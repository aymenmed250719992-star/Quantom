/**
 * NotificationContext — نظام الإشعارات الداخلي
 * يُدير قائمة الإشعارات ويُعرضها كبانرات عائمة
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useState,
} from "react";
import { View, StyleSheet } from "react-native";
import { NotificationBanner } from "@/components/NotificationBanner";
import type { AppNotification, NotifType } from "@/components/NotificationBanner";

interface NotificationContextType {
  notify: (type: NotifType, title: string, body: string) => void;
}

const NotificationContext = createContext<NotificationContextType>({
  notify: () => {},
});

export function useNotify() {
  return useContext(NotificationContext).notify;
}

let _idCounter = 0;
function makeId() { return `notif_${++_idCounter}_${Date.now()}`; }

export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const [queue, setQueue] = useState<AppNotification[]>([]);

  const notify = useCallback((type: NotifType, title: string, body: string) => {
    const notif: AppNotification = { id: makeId(), type, title, body };
    setQueue(prev => {
      // Max 3 visible at once
      const next = [...prev, notif];
      return next.length > 3 ? next.slice(next.length - 3) : next;
    });
  }, []);

  const dismiss = useCallback((id: string) => {
    setQueue(prev => prev.filter(n => n.id !== id));
  }, []);

  return (
    <NotificationContext.Provider value={{ notify }}>
      {children}
      {/* Banners are rendered above everything via position absolute */}
      <View style={styles.overlay} pointerEvents="box-none">
        {queue.map((n, i) => (
          <NotificationBanner
            key={n.id}
            notification={n}
            onDismiss={dismiss}
            index={i}
          />
        ))}
      </View>
    </NotificationContext.Provider>
  );
}

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 9999,
    pointerEvents: "box-none" as any,
  },
});
