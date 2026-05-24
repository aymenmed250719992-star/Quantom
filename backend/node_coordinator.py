"""
Node Coordinator — Multi-Server Leader Election — Quantom V2

Each server instance registers itself in the DB.
Only the LEADER runs the trading scheduler.
Standby nodes take over automatically if the leader goes silent (> 75s).

Free hosting setup:
  - Render (primary) → always-on with keep-alive ping
  - Railway / Fly.io / Koyeb (standby) → instant failover

All nodes share the same PostgreSQL DB and see each other's heartbeats.
"""
import asyncio
import os
import socket
import uuid
from datetime import datetime
from typing import Any, Callable, Optional


NODE_ID            = os.environ.get("NODE_ID") or f"{socket.gethostname()[:8]}-{str(uuid.uuid4())[:6]}"
HEARTBEAT_INTERVAL = 25    # seconds between heartbeats
LEADER_TIMEOUT     = 75    # seconds — if leader silent > this, take over
HOSTNAME           = socket.gethostname()


class NodeCoordinator:
    """
    Manages this server's role in a multi-server cluster.
    Singleton — get via NodeCoordinator.get_instance().
    """

    _instance: Optional["NodeCoordinator"] = None

    @classmethod
    def get_instance(cls) -> "NodeCoordinator":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self.node_id:     str  = NODE_ID
        self.hostname:    str  = HOSTNAME
        self.is_leader:   bool = False
        self._db:         Any  = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._scheduler_start_fn: Optional[Callable] = None
        self._scheduler_stop_fn:  Optional[Callable] = None
        print(f"[Node] ID={self.node_id} host={self.hostname}")

    def set_db(self, db: Any) -> None:
        self._db = db

    def set_scheduler_fns(self, start_fn: Callable, stop_fn: Callable) -> None:
        self._scheduler_start_fn = start_fn
        self._scheduler_stop_fn  = stop_fn

    async def start(self) -> None:
        """Register this node and start heartbeat + leader election."""
        if self._db is None:
            print("[Node] No DB — running as standalone leader")
            self.is_leader = True
            return
        try:
            await self._db.ensure_server_nodes_table()
            await self._db.register_server_node(self.node_id, self.hostname)
            await self._run_election()
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            print(f"[Node] Started — is_leader={self.is_leader}")
        except Exception as e:
            print(f"[Node] Start error: {e} — defaulting to leader")
            self.is_leader = True

    async def _run_election(self) -> None:
        """Check DB to decide if this node becomes leader."""
        try:
            nodes = await self._db.get_active_nodes(timeout_seconds=LEADER_TIMEOUT)
            leader = next((n for n in nodes if n.get("is_leader")), None)

            if leader is None:
                await self._db.set_node_leader(self.node_id)
                self.is_leader = True
                print(f"[Node] ✅ Became leader — no existing leader")
            elif leader.get("node_id") == self.node_id:
                self.is_leader = True
                print(f"[Node] ✅ Re-elected as leader")
            else:
                self.is_leader = False
                lhost = leader.get("hostname", "?")
                lid   = leader.get("node_id", "?")
                print(f"[Node] 👁 Standby — leader={lid} @ {lhost}")
        except Exception as e:
            print(f"[Node] Election error: {e} — defaulting to leader")
            self.is_leader = True

    async def _heartbeat_loop(self) -> None:
        """Send heartbeat every HEARTBEAT_INTERVAL seconds. Take over if leader dies."""
        while True:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                if self._db is None:
                    continue

                await self._db.update_node_heartbeat(self.node_id, self.is_leader)

                if not self.is_leader:
                    # Check if current leader is still alive
                    nodes  = await self._db.get_active_nodes(timeout_seconds=LEADER_TIMEOUT)
                    leader = next((n for n in nodes if n.get("is_leader") and n.get("node_id") != self.node_id), None)

                    if leader is None:
                        # Leader timed out → FAILOVER
                        await self._db.set_node_leader(self.node_id)
                        self.is_leader = True
                        print(f"[Node] 🔄 FAILOVER — {self.node_id} is now leader!")

                        # Auto-resume scheduler if bot was running
                        if self._scheduler_start_fn:
                            try:
                                bot_status = await self._db.get_bot_status()
                                if bot_status.get("is_running"):
                                    self._scheduler_start_fn()
                                    print(f"[Node] 🤖 Scheduler auto-resumed after failover")
                            except Exception as _e:
                                print(f"[Node] Auto-resume error: {_e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Node] Heartbeat error: {e}")

    async def stop(self) -> None:
        """Clean up on shutdown."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        if self._db and self.is_leader:
            try:
                await self._db.remove_server_node(self.node_id)
            except Exception:
                pass

    def get_status(self) -> dict:
        return {
            "node_id":   self.node_id,
            "hostname":  self.hostname,
            "is_leader": self.is_leader,
        }
