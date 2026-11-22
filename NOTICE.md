# Provider data in this repository

`pipeline/fixtures/raw/` and `pipeline/fixtures/sources/` hold responses saved from the providers on 2026-11-16, used only as test data, and `pipeline/fixtures/tree/` holds the expected output the tests build from them. They are not a publication of these datasets, and the MIT License of the code does not apply to them. Each remains under its provider's terms:

| Data | Provider | Terms |
|---|---|---|
| Effective Federal Funds Rate (`nyfed-effr-full.json.gz`, `effr-*.json`, and the files of `pipeline/fixtures/tree/`) | Federal Reserve Bank of New York | https://www.newyorkfed.org/privacy/termsofuse. © 2026 Federal Reserve Bank of New York. Content from the New York Fed subject to the Terms of Use at newyorkfed.org. The Effective Federal Funds Rate (EFFR) is subject to the Terms of Use posted at newyorkfed.org. The New York Fed is not responsible for publication of the EFFR by RadMage Finance, does not sanction or endorse any particular republication, and has no liability for your use. These files are redistributed with the same permissions, conditions and restrictions as the New York Fed's Terms of Use; the fixture scenario's synthetic values are modified content and are labeled as such below. |
| Debt to the Penny (`fiscaldata-*.json*`, `dtp-*.json`) | U.S. Department of the Treasury, Bureau of the Fiscal Service | https://fiscaldata.treasury.gov/api-documentation/ |
| H.6 Money Stock Measures (`frb-h6-*`, `h6-*.json`) | Board of Governors of the Federal Reserve System | https://www.federalreserve.gov/disclaimer.htm |

Values after the saved data in the fixture scenario are synthetic and exist only to exercise a rule; they are not provider data.

The files of `pipeline/fixtures/tree/` name the New York Fed's earlier terms address, https://www.newyorkfed.org/termsofuse, because the tests pin their bytes. The same terms are now at https://www.newyorkfed.org/privacy/termsofuse.
