"""Market-specific machinery, where an asset class needs more than a config.

Equities, crypto and generic futures are handled by configuration. EU ETS carbon
is not: its tradable universe is one instrument, so the lab's cross-sectional
evaluation is undefined on it, and its interesting free data is auction results
rather than prices. `euets` supplies both halves.
"""
