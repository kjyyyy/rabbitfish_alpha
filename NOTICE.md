# NOTICE

Research software. It does not place orders and nothing here is financial advice.

This file is attribution and data-terms, not a second licence. The code is MIT
(see `LICENSE`). Terms that apply to third-party software or to market data are
those of their owners; they do not relicense this project.

## Third-party software

### Microsoft Qlib

[Microsoft Qlib](https://github.com/microsoft/qlib) is MIT licensed. This project
depends on the PyPI distribution `pyqlib`; Qlib is not vendored here.

### AlphaGen and AlphaForge

[AlphaGen](https://github.com/ICT-FinD-Lab/alphagen) (`ICT-FinD-Lab/alphagen`) and
[AlphaForge](https://github.com/DulyHao/AlphaForge) (`DulyHao/AlphaForge`) publish
no licence file (GitHub reports no licence; `LICENSE` is absent on the default
branch of each). Their ideas are re-implemented from the papers. No code was
copied from either project.

### MiroFish

[MiroFish](https://github.com/666ghj/MiroFish) is licensed under the GNU Affero
General Public License v3.0. It is deliberately not used, in code or as a
dependency.

### Direct Python dependencies

The table below was generated from `importlib.metadata` after
`pip install -e ".[qlib,llm,dev,web,postgres]"`. It lists every direct dependency
declared in `pyproject.toml` (core and extras). Values are what each installed
distribution reports about itself (`License-Expression`, else `Classifier`, else
`License`), not an independent legal opinion. Transitive dependencies are omitted.

| Package | Extra | Installed version | Licence | Metadata field |
|---------|-------|-------------------|---------|----------------|
| numpy | (core) | 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | License-Expression |
| pandas | (core) | 3.0.6 | BSD License | Classifier |
| scipy | (core) | 1.17.1 | BSD License | Classifier |
| PyYAML | (core) | 6.0.3 | MIT License | Classifier |
| pydantic | (core) | 2.13.5 | MIT | License-Expression |
| lightgbm | (core) | 4.7.0 | MIT | License-Expression |
| matplotlib | (core) | 3.11.2 | Python Software Foundation License | Classifier |
| scikit-learn | (core) | 1.9.1 | BSD-3-Clause | License-Expression |
| SQLAlchemy | (core) | 2.0.54 | MIT | License |
| alembic | (core) | 1.20.0 | MIT | License-Expression |
| pyqlib | extra | 0.9.7 | MIT License | Classifier |
| psycopg | extra | 3.3.6 | LGPL-3.0-only | License-Expression |
| anthropic | extra | 1.8.0 | MIT License | Classifier |
| openai | extra | 3.18.0 | Apache-2.0 | License-Expression |
| fastapi | extra | 0.141.1 | MIT | License-Expression |
| uvicorn | extra | 0.53.0 | BSD-3-Clause | License-Expression |
| Jinja2 | extra | 3.1.6 | BSD License | Classifier |
| pytest | extra | 9.1.1 | MIT | License-Expression |
| ruff | extra | 0.16.8 | MIT | License-Expression |

`psycopg` (optional `postgres` extra) reports `LGPL-3.0-only`. It is not a core
dependency.

## Data licences

This repository ships no market data, and none should ever be committed. Users
are responsible for the terms of whatever they fetch. **These terms attach to
the data, not to this MIT-licensed code.**

- **EEX auction reports.** Public download, but EEX terms bar "systematic
  republication or dissemination of a substantial amount of the Data". Fetch for
  research; do not redistribute or commit.
- **ENTSO-E Transparency Platform.** ENTSO-E terms apply. The CC-BY-4.0 claim
  covers the open-data list only; redistribution rights for other series are
  unverified. Access requires a personal API token, which the user obtains
  themselves.
- **Zenodo EU ETS Data Package.** CC-BY-4.0; redistributable with attribution.
- **Open-Meteo / ECMWF open data.** CC-BY-4.0. This refers to the weather data
  (ECMWF open data is CC-BY-4.0; Open-Meteo redistributes that class of open
  data). It does not refer to Open-Meteo's own software, which this project does
  not depend on.
- **TTF gas and API2 coal.** Commercial, not free, not included.
