# Strategy Support Matrix

Spreadsheet source: `trading_strategies_master_map_v2.xlsx` (`Master_Strategies` sheet).

The machine-readable source of truth is `src/strategies/strategy_manifest.json`.

## Summary Counts

- Total spreadsheet strategies: **250**
- Fully implemented: **32**
- Limited implementation: **47**
- Deferred: **143**
- Not strategy-layer (portfolio/execution): **28**

## Category Breakdown

| Category | Full | Limited | Deferred | Not-Strategy-Layer | Total |
|---|---:|---:|---:|---:|---:|
| etf_index | 7 | 9 | 8 | 1 | 25 |
| event_driven | 0 | 3 | 18 | 0 | 21 |
| forex | 4 | 5 | 6 | 0 | 15 |
| futures | 8 | 4 | 18 | 0 | 30 |
| intraday | 7 | 16 | 5 | 0 | 28 |
| options | 0 | 0 | 61 | 15 | 76 |
| positional | 0 | 0 | 1 | 0 | 1 |
| quant | 3 | 1 | 9 | 0 | 13 |
| relative_value | 0 | 2 | 12 | 1 | 15 |
| swing | 3 | 7 | 5 | 0 | 15 |
| unsupported | 0 | 0 | 0 | 11 | 11 |

## Runnable Strategy Mappings

| Strategy ID | Spreadsheet Name | Classification | Registry Key | Class | Category |
|---|---|---|---|---|---|
| S006 | Opening Drive | limited | `opening_range_breakout` | `OpeningRangeBreakoutStrategy` | intraday |
| S007 | Opening Range Breakout | full | `opening_range_breakout` | `OpeningRangeBreakoutStrategy` | intraday |
| S008 | Opening Range Breakdown | full | `opening_range_breakdown` | `OpeningRangeBreakoutStrategy` | intraday |
| S009 | VWAP Pullback Long | limited | `vwap_pullback_long` | `VWAPPullbackTrendStrategy` | intraday |
| S010 | VWAP Breakdown Retest Short | limited | `vwap_breakdown_retest_short` | `VWAPPullbackTrendStrategy` | intraday |
| S011 | VWAP Mean Reversion | full | `vwap_mean_reversion` | `VWAPMeanReversionStrategy` | intraday |
| S012 | Gap and Go | full | `gap_and_go` | `GapMomentumStrategy` | intraday |
| S013 | Gap Fade | full | `gap_fade` | `GapFadeStrategy` | intraday |
| S014 | High-of-Day Momentum Breakout | limited | `day_high_breakout` | `DayHighLowBreakoutStrategy` | intraday |
| S015 | Low-of-Day Breakdown | limited | `day_low_breakdown` | `DayHighLowBreakoutStrategy` | intraday |
| S016 | Support Bounce | limited | `pivot_point_reversal` | `PivotPointReversalStrategy` | intraday |
| S017 | Resistance Rejection | limited | `pivot_point_reversal` | `PivotPointReversalStrategy` | intraday |
| S018 | Trendline Break Retest | limited | `intraday_trend_following` | `IntradayTrendFollowingStrategy` | intraday |
| S019 | Flag Breakout Intraday | limited | `price_channel_breakout` | `PriceChannelBreakoutStrategy` | swing |
| S020 | Pullback Continuation | limited | `moving_average_pullback` | `MovingAveragePullbackStrategy` | swing |
| S021 | News Spike Follow-Through | limited | `day_high_breakout` | `DayHighLowBreakoutStrategy` | intraday |
| S022 | Earnings Day Momentum | limited | `day_high_breakout` | `DayHighLowBreakoutStrategy` | intraday |
| S023 | Sector Sympathy Trade | limited | `relative_strength_rotation_limited` | `RelativeStrengthRotationStrategy` | quant |
| S024 | Relative Volume Breakout | full | `relative_volume_breakout` | `RelativeVolumeBreakoutStrategy` | intraday |
| S025 | Lunch-Hour Range Fade | limited | `vwap_mean_reversion` | `VWAPMeanReversionStrategy` | intraday |
| S026 | Power-Hour Trend | limited | `intraday_trend_following` | `IntradayTrendFollowingStrategy` | intraday |
| S027 | Index-Led Beta Trade | limited | `relative_strength_rotation_limited` | `RelativeStrengthRotationStrategy` | quant |
| S028 | TICK / Breadth Trend Trade | limited | `intraday_trend_following` | `IntradayTrendFollowingStrategy` | intraday |
| S030 | Pairs Trading Intraday | limited | `pairs_intraday_limited` | `PairsZScoreStrategy` | relative_value |
| S031 | Statistical Reversion Basket | limited | `statistical_reversion_basket_limited` | `PairsZScoreStrategy` | quant |
| S032 | Overnight Gap Fill (same day) | limited | `gap_fade` | `GapFadeStrategy` | intraday |
| S033 | Pivot Point Reversal | full | `pivot_point_reversal` | `PivotPointReversalStrategy` | intraday |
| S034 | Market Profile Initial Balance Break | limited | `opening_range_breakout` | `OpeningRangeBreakoutStrategy` | intraday |
| S036 | ETF Lead-Lag Rotation | limited | `etf_lead_lag_rotation_limited` | `RelativeStrengthRotationStrategy` | etf_index |
| S037 | Pullback to 20DMA | full | `pullback_to_20dma` | `MovingAveragePullbackStrategy` | swing |
| S038 | Pullback to 50DMA | full | `pullback_to_50dma` | `MovingAveragePullbackStrategy` | swing |
| S039 | Breakout from Base | limited | `price_channel_breakout` | `PriceChannelBreakoutStrategy` | swing |
| S041 | Volatility Contraction Pattern | limited | `price_channel_breakout` | `PriceChannelBreakoutStrategy` | swing |
| S042 | Flag / Pennant Swing Breakout | limited | `price_channel_breakout` | `PriceChannelBreakoutStrategy` | swing |
| S043 | Channel Breakout | full | `price_channel_breakout` | `PriceChannelBreakoutStrategy` | swing |
| S044 | Donchian Swing Breakout | full | `donchian_swing_breakout` | `PriceChannelBreakoutStrategy` | swing |
| S045 | RSI Oversold Bounce | full | `rsi_reversion` | `RSIReversionStrategy` | swing |
| S046 | Bollinger Band Reversion | full | `bollinger_reversion` | `BollingerReversionStrategy` | swing |
| S047 | Gap Fill Swing | limited | `gap_fade` | `GapFadeStrategy` | intraday |
| S048 | Earnings Drift Swing | limited | `momentum_investing` | `TimeSeriesMomentumStrategy` | positional |
| S050 | Relative Strength Leaders | limited | `relative_strength_rotation_limited` | `RelativeStrengthRotationStrategy` | quant |
| S051 | Sector Rotation Swing | limited | `sector_rotation_swing_limited` | `RelativeStrengthRotationStrategy` | etf_index |
| S052 | IPO Base Breakout | limited | `price_channel_breakout` | `PriceChannelBreakoutStrategy` | swing |
| S053 | Failed Breakdown Reversal | limited | `bollinger_reversion` | `BollingerReversionStrategy` | swing |
| S056 | Breakout Retest Entry | limited | `price_channel_breakout` | `PriceChannelBreakoutStrategy` | swing |
| S057 | Weekly Momentum Continuation | full | `weekly_momentum_continuation` | `TimeSeriesMomentumStrategy` | swing |
| S058 | 52-Week High Breakout | full | `high_52_week_breakout` | `PriceChannelBreakoutStrategy` | positional |
| S060 | ETF Rotation Swing | limited | `relative_strength_rotation_limited` | `RelativeStrengthRotationStrategy` | quant |
| S061 | Pairs Trade Swing | limited | `pairs_trade_swing_limited` | `PairsZScoreStrategy` | relative_value |
| S062 | Long-Term Trend Following | full | `long_term_trend_following` | `LongTermTrendStrategy` | positional |
| S063 | 200DMA Trend Model | full | `trend_200dma_model` | `LongTermTrendStrategy` | positional |
| S064 | Dual Moving Average Crossover | full | `sma_crossover` | `SMACrossoverStrategy` | positional |
| S065 | Turtle / Donchian Breakout | full | `turtle_donchian_breakout` | `PriceChannelBreakoutStrategy` | positional |
| S066 | Momentum Investing | full | `momentum_investing` | `TimeSeriesMomentumStrategy` | positional |
| S067 | Cross-Sectional Momentum Rotation | limited | `cross_sectional_momentum_rotation_limited` | `RelativeStrengthRotationStrategy` | quant |
| S078 | Sector Rotation Macro | limited | `sector_rotation_swing_limited` | `RelativeStrengthRotationStrategy` | etf_index |
| S092 | Futures Opening Range Breakout | full | `futures_opening_range_breakout` | `OpeningRangeBreakoutStrategy` | futures |
| S093 | Trend-Day Pullback (Futures) | full | `futures_trend_pullback` | `MovingAveragePullbackStrategy` | futures |
| S094 | Reversion to Settlement / VWAP | limited | `futures_vwap_reversion_limited` | `VWAPMeanReversionStrategy` | futures |
| S096 | Breakout from Balance Area | limited | `futures_opening_range_breakout` | `OpeningRangeBreakoutStrategy` | futures |
| S098 | Outright Trend Following (Futures) | full | `futures_outright_trend_following` | `TimeSeriesMomentumStrategy` | futures |
| S099 | Futures Breakout System | full | `futures_breakout_system` | `PriceChannelBreakoutStrategy` | futures |
| S100 | Futures Pullback Trend | full | `futures_pullback_trend` | `MovingAveragePullbackStrategy` | futures |
| S114 | Precious Metals Safe-Haven Breakout | limited | `precious_metals_breakout_limited` | `PriceChannelBreakoutStrategy` | commodities |
| S117 | FX Trend Following | full | `fx_trend_following` | `TimeSeriesMomentumStrategy` | forex |
| S118 | FX Breakout on Macro Data | limited | `fx_breakout_on_macro_data_limited` | `OpeningRangeBreakoutStrategy` | forex |
| S119 | FX Range Trading | full | `fx_range_trading` | `BollingerReversionStrategy` | forex |
| S120 | FX Mean Reversion | full | `fx_mean_reversion` | `BollingerReversionStrategy` | forex |
| S123 | Risk-On / Risk-Off FX Basket | limited | `risk_on_risk_off_fx_basket_limited` | `RelativeStrengthRotationStrategy` | forex |
| S124 | G10 Relative Strength Basket | limited | `g10_relative_strength_limited` | `RelativeStrengthRotationStrategy` | forex |
| S126 | London Breakout | full | `london_breakout` | `OpeningRangeBreakoutStrategy` | forex |
| S127 | Asian Range Fade | limited | `asian_range_fade_limited` | `BollingerReversionStrategy` | forex |
| S129 | FX Statistical Pairs | limited | `fx_statistical_pairs_limited` | `PairsZScoreStrategy` | forex |
| S139 | Crypto Trend Following | full | `crypto_trend_following` | `TimeSeriesMomentumStrategy` | quant |
| S140 | Crypto Breakout | full | `crypto_breakout` | `PriceChannelBreakoutStrategy` | quant |
| S141 | Crypto Mean Reversion | full | `crypto_mean_reversion` | `BollingerReversionStrategy` | quant |
| S145 | Alt/BTC Relative Strength | limited | `alt_btc_relative_strength_limited` | `RelativeStrengthRotationStrategy` | quant |
| S149 | Cointegration Pairs Trading | limited | `cointegration_pairs_limited` | `PairsZScoreStrategy` | relative_value |
| S150 | Basket Statistical Arbitrage | limited | `statistical_reversion_basket_limited` | `PairsZScoreStrategy` | quant |

## Deferred / Non-Strategy Guidance

- Deferred rows are intentionally not registered as runnable to avoid misleading capability claims.
- `not_strategy_layer` rows are execution/portfolio/overlay constructs and belong outside BaseStrategy signal generation.
- Infra requirements per deferred row are documented in `src/strategies/strategy_manifest.json`.
