"""Reference 'alpha zoo' for originality checks: Qlib's Alpha158 expressions
(+ whatever is already in the library). A new factor whose largest common
subtree with the zoo exceeds gates.max_zoo_overlap is a near-duplicate."""


def alpha158_exprs():
    try:
        from qlib.contrib.data.loader import Alpha158DL
        fields, _ = Alpha158DL.get_feature_config()
        return list(fields)
    except Exception:          # qlib not installed (e.g. CI) -> small built-in zoo
        return ["$close/Ref($close,5)-1", "Std($close,20)/$close", "Mean($close,20)/$close",
                "Corr($close,Log($volume+1),20)", "Max($high,20)/$close", "Min($low,20)/$close"]
