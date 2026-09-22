"""Hypothesis-first factors: each has an economic reason written down BEFORE
testing. Sign = the direction the hypothesis predicts (+1 higher value -> higher
future return). Getting the sign wrong counts as a failed hypothesis."""

RET1 = "($close/Ref($close,1)-1)"

HYPOTHESES = [
    dict(name="mom_12_1", sign=+1, expr="Ref($close,20)/Ref($close,240)-1",
         rationale="12-1 month momentum: slow diffusion of information (Jegadeesh-Titman). "
                   "A-shares are known for weak momentum - a genuine test."),
    dict(name="rev_5d", sign=-1, expr="$close/Ref($close,5)-1",
         rationale="Short-term reversal: liquidity provision to retail-driven overreaction."),
    dict(name="rev_20d", sign=-1, expr="$close/Ref($close,20)-1",
         rationale="1-month reversal: overreaction by attention-driven traders."),
    dict(name="low_vol_20d", sign=-1, expr=f"Std({RET1},20)",
         rationale="Low-volatility anomaly: leverage-constrained / lottery-seeking investors overpay for risky stocks."),
    dict(name="max_ret_20d", sign=-1, expr=f"Max({RET1},20)",
         rationale="MAX effect (Bali-Cakici-Whitelaw): lottery-like stocks are overpriced."),
    dict(name="abn_turnover", sign=-1, expr="Mean($volume,20)/Mean($volume,120)",
         rationale="Attention-driven buying: abnormal volume marks crowded retail interest."),
    dict(name="amihud_illiq", sign=+1, expr=f"Mean(Abs({RET1})/($amount+1),20)",
         rationale="Illiquidity premium (Amihud 2002): compensation for trading costs."),
    dict(name="near_52w_high", sign=+1, expr="$close/Max($high,240)",
         rationale="52-week-high anchoring (George-Hwang): investors under-react near the high."),
    dict(name="pv_corr_20d", sign=-1, expr="Corr($close,Log($volume+1),20)",
         rationale="Price-volume correlation: volume-confirmed moves by noise traders tend to reverse."),
    dict(name="skew_20d", sign=-1, expr=f"Skew({RET1},20)",
         rationale="Skewness preference: positively skewed stocks are overpriced."),
    dict(name="vwap_gap", sign=-1, expr="$close/$vwap-1",
         rationale="Close above VWAP = late-day buying pressure that mean-reverts."),
    dict(name="hl_range_20d", sign=-1, expr="Mean(($high-$low)/$close,20)",
         rationale="Intraday range as a volatility/uncertainty proxy (low-risk anomaly)."),
]
