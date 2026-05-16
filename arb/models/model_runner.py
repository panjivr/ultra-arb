"""
Scheduled model refresh runner.
HMM: every 15 minutes.
Cointegration: every 1 hour.
Bayesian: every 100 trades (polled every 5 min).
"""
import asyncio
from arb.models.hmm import RegimeDetector
from arb.models.cointegration import CointegrationScanner
from arb.models.bayesian import BayesianWinRateEstimator
from arb.infra.redis_bus import publish
import time

HMM_INTERVAL = 15 * 60
COINT_INTERVAL = 60 * 60
BAYES_INTERVAL = 5 * 60


class ModelRunner:
    def __init__(self) -> None:
        self.regime_detector = RegimeDetector()
        self.cointegration = CointegrationScanner()
        self.bayesian = BayesianWinRateEstimator()
        self._current_regime = 1

    @property
    def current_regime(self) -> int:
        return self._current_regime

    async def start(self) -> None:
        self.regime_detector.fit_synthetic()
        print("[model_runner] Initial HMM trained on synthetic data")
        await asyncio.gather(
            self._hmm_loop(),
            self._coint_loop(),
            self._bayes_loop(),
        )

    async def _hmm_loop(self) -> None:
        while True:
            try:
                regime = await self.regime_detector.update()
                self._current_regime = regime
                await publish("arb:signals", {
                    "ts": int(time.time() * 1000),
                    "strategy": "ModelRunner",
                    "event": "regime_update",
                    "regime": regime,
                })
                print(f"[model_runner] Regime updated: {regime} (0=low, 1=med, 2=high vol)")
            except Exception as e:
                print(f"[model_runner] HMM error: {e}")
            await asyncio.sleep(HMM_INTERVAL)

    async def _coint_loop(self) -> None:
        while True:
            try:
                result = await self.cointegration.scan()
                print(
                    f"[model_runner] Cointegration: cointegrated={result.get('cointegrated')} "
                    f"z={result.get('z_score', 0):.2f} hedge={result.get('hedge_ratio', 1):.4f}"
                )
            except Exception as e:
                print(f"[model_runner] Cointegration error: {e}")
            await asyncio.sleep(COINT_INTERVAL)

    async def _bayes_loop(self) -> None:
        while True:
            try:
                await self.bayesian.refresh_from_db()
            except Exception as e:
                print(f"[model_runner] Bayesian error: {e}")
            await asyncio.sleep(BAYES_INTERVAL)
