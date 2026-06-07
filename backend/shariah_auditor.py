"""
ShariahAuditor — فلتر الامتثال الإسلامي الكامل لـ Quantom V2

يفحص كل رمز قبل التداول ضد:
  1. القائمة السوداء المباشرة (محظور قطعياً)
  2. فئات محظورة (قمار، كحول، ربا، محتوى بالغ)
  3. رموز مشبوهة / FOMO / meme tokens بلا قيمة جوهرية
  4. رموز قائمة على الفائدة (staking rewards يُعاد توزيعها كفائدة)

المصدر: مبادئ التمويل الإسلامي وقرارات هيئة المحاسبة والمراجعة للمؤسسات المالية الإسلامية (AAOIFI)
"""

import re
from typing import Optional

# ─── قائمة سوداء مباشرة ──────────────────────────────────────────────────────
# رموز محظورة قطعياً بسبب طبيعة مشاريعها
BLACKLIST_EXACT: frozenset[str] = frozenset({
    # قمار / Gambling
    "DICE", "ROLL", "WINK", "LUCKY", "JACKPOT", "CASINO", "SLOT",
    "BET", "DBET", "SPORT", "SBCH", "DRAFTCOIN",
    # كحول / Alcohol
    "WINE", "BEER", "BREW", "WHISKY", "GIN",
    # فوائد ربوية صريحة / Explicit Interest
    "cUSDT", "cDAI", "cETH", "cWBTC",  # Compound interest tokens
    "aUSDT", "aDAI", "aETH", "aWBTC",  # Aave interest-bearing
    "sUSD", "sFRAX",                     # Synth interest
    # محتوى بالغ / Adult content
    "SEXY", "PORN", "XXX", "ADULT", "VENUS",
    # ميم بلا قيمة جوهرية موثّقة / Pure speculation memes
    "PEPE2", "CHAD", "WOJAK", "BOOMER",
})

# ─── أنماط محظورة ────────────────────────────────────────────────────────────
# أي رمز يحتوي على هذه الكلمات المفتاحية
BLACKLIST_PATTERNS: tuple[re.Pattern, ...] = tuple(
    re.compile(p, re.IGNORECASE) for p in [
        r"\bbet\b", r"\bgambl", r"\bcasino\b", r"\blotter",
        r"\bbeer\b", r"\bwine\b", r"\bwhisk", r"\bvodka",
        r"\bporn\b", r"\bsex(?!tech)\b", r"\bxxx\b",
        r"\bribba\b", r"\briba\b",
        r"^c(usdt|dai|eth|wbtc|usdc)$",   # Compound wrapped
        r"^a(usdt|dai|eth|wbtc|usdc)$",   # Aave wrapped
    ]
)

# ─── رموز مسموح بها صراحةً (whitelist) ─────────────────────────────────────
# أشهر العملات التي درسها العلماء وأُجيز التداول فيها
WHITELIST_EXACT: frozenset[str] = frozenset({
    # Layer 1
    "BTC", "ETH", "BNB", "SOL", "ADA", "AVAX", "DOT", "ATOM",
    "NEAR", "ALGO", "FTM", "ONE", "EGLD", "HBAR", "XTZ",
    # Layer 2 / Scaling
    "MATIC", "POL", "ARB", "OP", "LRC", "IMX", "STRK",
    # DeFi (وظيفي)
    "UNI", "AAVE", "CRV", "MKR", "SNX", "SUSHI", "COMP",
    "LDO", "RPL", "BAL", "CAKE", "1INCH",
    # Infrastructure
    "LINK", "GRT", "API3", "BAND", "VET", "THETA", "FIL",
    "AR", "STORJ", "SC", "BTT",
    # Exchange tokens
    "BNB", "OKB", "HT", "CRO", "KCS", "GT",
    # Stablecoins
    "USDT", "USDC", "BUSD", "TUSD", "DAI", "FDUSD",
    # Popular
    "LTC", "XRP", "DOGE", "SHIB", "TRX", "XLM", "XMR",
    "DASH", "ZEC", "ETC", "BCH", "BSV",
    # AI / Tech
    "FET", "AGIX", "OCEAN", "RLC", "NMR", "RNDR",
    # Gaming (blockchain)
    "AXS", "SAND", "MANA", "ENJ", "GALA", "ILV", "MAGIC",
    # Oracles / Data
    "BAND", "TRB", "DIA",
    # Meme (major, مشهور ومدروس)
    "DOGE", "SHIB", "FLOKI", "PEPE", "WIF", "BONK",
})

# ─── الحكم ────────────────────────────────────────────────────────────────────

_HALAL   = "HALAL"
_HARAM   = "HARAM"
_CAUTION = "CAUTION"   # شبهة — يمكن التداول بحذر مع التوثيق


class ShariahAuditResult:
    __slots__ = ("symbol", "verdict", "reason", "confidence")

    def __init__(self, symbol: str, verdict: str, reason: str, confidence: float = 1.0):
        self.symbol     = symbol
        self.verdict    = verdict
        self.reason     = reason
        self.confidence = confidence  # 0.0 – 1.0

    @property
    def is_halal(self) -> bool:
        return self.verdict == _HALAL

    @property
    def is_haram(self) -> bool:
        return self.verdict == _HARAM

    def to_dict(self) -> dict:
        return {
            "symbol":     self.symbol,
            "verdict":    self.verdict,
            "reason":     self.reason,
            "confidence": self.confidence,
            "is_halal":   self.is_halal,
        }

    def __repr__(self) -> str:
        icon = "✅" if self.is_halal else ("❌" if self.is_haram else "⚠️")
        return f"[Shariah] {icon} {self.symbol} → {self.verdict}: {self.reason}"


class ShariahAuditor:
    """
    مدقق الامتثال الإسلامي — singleton.
    استخدم: ShariahAuditor.get_instance().audit("BTC/USDT")
    """

    _instance: Optional["ShariahAuditor"] = None

    @classmethod
    def get_instance(cls) -> "ShariahAuditor":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ─────────────────────────────────────────────────────────────────────────

    def _extract_base(self, symbol: str) -> str:
        """BTC/USDT → BTC | BTCUSDT → BTC"""
        clean = symbol.upper().strip()
        if "/" in clean:
            return clean.split("/")[0]
        for quote in ("USDT", "USDC", "BTC", "ETH", "BNB", "BUSD"):
            if clean.endswith(quote) and len(clean) > len(quote):
                return clean[: -len(quote)]
        return clean

    def audit(self, symbol: str) -> ShariahAuditResult:
        base = self._extract_base(symbol)

        # 1. قائمة السماح الصريحة
        if base in WHITELIST_EXACT:
            return ShariahAuditResult(
                base, _HALAL,
                f"{base} مدرج في قائمة العملات المعتمدة إسلامياً",
                confidence=0.95,
            )

        # 2. القائمة السوداء الصريحة
        if base in BLACKLIST_EXACT:
            return ShariahAuditResult(
                base, _HARAM,
                f"{base} مدرج في قائمة العملات المحظورة إسلامياً",
                confidence=1.0,
            )

        # 3. فحص الأنماط المحظورة
        for pattern in BLACKLIST_PATTERNS:
            if pattern.search(base):
                return ShariahAuditResult(
                    base, _HARAM,
                    f"{base} يحتوي على نمط محظور شرعاً ({pattern.pattern})",
                    confidence=0.9,
                )

        # 4. رموز wrapped interest-bearing
        if base.startswith(("c", "a", "s")) and len(base) > 2:
            underlying = base[1:].upper()
            if underlying in WHITELIST_EXACT and underlying not in ("ADA", "SOL"):
                return ShariahAuditResult(
                    base, _HARAM,
                    f"{base} يبدو أنه رمز فائدة ملفوف (interest-bearing wrapped) — محظور",
                    confidence=0.8,
                )

        # 5. رموز مجهولة غير مدرجة — تحذير
        return ShariahAuditResult(
            base, _CAUTION,
            f"{base} غير مدرج في قوائمنا المعروفة — يُنصح بالتحقق اليدوي من المشروع",
            confidence=0.6,
        )

    def is_tradeable(self, symbol: str, allow_caution: bool = False) -> bool:
        """True إذا كان مسموحاً بالتداول."""
        result = self.audit(symbol)
        if result.verdict == _HALAL:
            return True
        if allow_caution and result.verdict == _CAUTION:
            return True
        return False

    def bulk_audit(self, symbols: list[str]) -> dict[str, ShariahAuditResult]:
        return {sym: self.audit(sym) for sym in symbols}

    def filter_halal(self, symbols: list[str], allow_caution: bool = True) -> list[str]:
        """إرجاع فقط الرموز المسموح بتداولها."""
        return [s for s in symbols if self.is_tradeable(s, allow_caution=allow_caution)]


# ─── Convenience ─────────────────────────────────────────────────────────────

def audit_symbol(symbol: str) -> ShariahAuditResult:
    return ShariahAuditor.get_instance().audit(symbol)


def is_halal(symbol: str, allow_caution: bool = True) -> bool:
    return ShariahAuditor.get_instance().is_tradeable(symbol, allow_caution)
