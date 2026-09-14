# Presentation-only report layer

Not part of the frozen executable pack (`harness/pack.py` FREEZE_RELATIVE).
Do not import this package from frozen analysis. Statistics come from
`harness/analysis.py` only. Plots may use matplotlib; the frozen
`harness/report.py` SVG helper is not used for official figures.
