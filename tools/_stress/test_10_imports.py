"""(b) Import-graph + back-compat shim identity + public-API signature pins.

A future orchestrator relies on these surfaces; a shim that forks (loses identity) or a
signature drift fails loudly HERE. (The import-linter dependency-direction contract is
checked by run_stress.sh + the CI workflow, not in-process.)
"""
import importlib
import inspect

import pytest

pytestmark = pytest.mark.stress

_CORE_MODULES = [
    "tools.core.gemini.client", "tools.core.gemini.config",
    "tools.core.webflow.http", "tools.core.webflow.cms",
    "tools.core.web.page_fetcher", "tools.core.content.structure",
    "tools.core.seo.llms_parser",
]


def test_core_modules_import_standalone():
    for m in _CORE_MODULES:
        importlib.import_module(m)


def test_back_compat_shims_preserve_identity():
    import tools.core.gemini.client as cc
    import tools.summary.batch_runner as br
    assert br.submit_batch is cc.submit_batch
    assert br._PENDING_BATCHES is cc._PENDING_BATCHES  # shared mutable state, not a fork

    import tools.core.web.page_fetcher as cpf
    import tools.summary.page_fetcher as pf
    assert pf.fetch_page is cpf.fetch_page

    import tools.core.content.structure as cst
    import tools.summary.structure as st
    assert st.summary_markdown_to_html is cst.summary_markdown_to_html

    import tools.core.seo.llms_parser as clp
    import tools.summary.llms_parser as lp
    assert lp.LlmsIndex is clp.LlmsIndex

    from tools.core.webflow.cms import CmsClient, WriteResult
    import tools.summary.webflow_client as wc
    assert wc.WriteResult is WriteResult and issubclass(wc.WebflowClient, CmsClient)

    import tools.core.gemini.config as gc
    import tools.summary.config as sc
    assert sc.MODEL_ID is gc.MODEL_ID and sc.LAST_BATCH_FILE is gc.LAST_BATCH_FILE


def test_public_signatures_pinned():
    from tools.core.gemini.client import BatchRequest, submit_batch
    assert list(inspect.signature(BatchRequest).parameters)[:3] == ["custom_id", "system_blocks", "user_message"]
    assert list(inspect.signature(submit_batch).parameters) == ["requests", "api_key_env", "model"]

    from tools.core.webflow.cms import CmsClient
    assert list(inspect.signature(CmsClient.patch_fields).parameters) == ["self", "collection_id", "item_id", "field_data"]

    from tools.translator import translate_batch
    tp = inspect.signature(translate_batch).parameters
    assert "units" in tp and "target_locale" in tp and "dry_run" in tp

    from tools.copywriter import improve_copy
    cp = list(inspect.signature(improve_copy).parameters)
    assert cp[0] == "req" and "dry_run" in cp
