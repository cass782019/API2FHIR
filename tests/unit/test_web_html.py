"""Testes unitários — validação estrutural do HTML da UI web."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_HTML = Path(__file__).parents[2] / "apps" / "web" / "static" / "index.html"


@pytest.fixture(scope="module")
def html() -> str:
    return _HTML.read_text(encoding="utf-8")


# ── Existência e parseabilidade ───────────────────────────────────────────────


@pytest.mark.unit
def test_html_file_exists() -> None:
    assert _HTML.exists(), f"Não encontrado: {_HTML}"


@pytest.mark.unit
def test_html_is_parseable(html: str) -> None:
    from html.parser import HTMLParser

    HTMLParser().feed(html)  # lança se estrutura inválida


# ── Elementos obrigatórios da UI ──────────────────────────────────────────────


@pytest.mark.unit
def test_has_file_input(html: str) -> None:
    assert "file-input" in html


@pytest.mark.unit
def test_has_convert_button(html: str) -> None:
    assert "convert-btn" in html


@pytest.mark.unit
def test_has_download_button(html: str) -> None:
    assert "download-btn" in html


@pytest.mark.unit
def test_has_model_select(html: str) -> None:
    assert "model-select" in html


@pytest.mark.unit
def test_has_hapi_url_input(html: str) -> None:
    assert "hapi-url" in html


@pytest.mark.unit
def test_has_spinner(html: str) -> None:
    assert "spinner" in html


@pytest.mark.unit
def test_has_error_box(html: str) -> None:
    assert "error-box" in html


# ── Modelos disponíveis ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_model_opus_present(html: str) -> None:
    assert "claude-opus-4-7" in html


@pytest.mark.unit
def test_model_haiku_present(html: str) -> None:
    assert "claude-haiku-4-5-20251001" in html


@pytest.mark.unit
def test_model_sabia_present(html: str) -> None:
    assert "sabia-4" in html


# ── Segurança / privacidade ───────────────────────────────────────────────────


@pytest.mark.unit
def test_no_external_scripts(html: str) -> None:
    """Apenas o Monaco editor (CDN whitelisted) é permitido como script externo."""
    found = re.findall(r'<script[^>]+src=["\']https?://([^/"\']+)', html)
    allowed = {"cdn.jsdelivr.net"}
    unauthorized = [host for host in found if host not in allowed]
    assert not unauthorized, f"Scripts externos não autorizados: {unauthorized}"


@pytest.mark.unit
def test_no_external_styles(html: str) -> None:
    """Proibido carregar CSS de CDNs externos."""
    found = re.findall(r'<link[^>]+href=["\']https?://', html)
    assert not found, f"Estilos externos encontrados: {found}"


@pytest.mark.unit
def test_fetch_uses_relative_url(html: str) -> None:
    """fetch deve usar URLs relativas — nginx faz o proxy para a API."""
    expected = ["/v1/detect", "/v1/infer-spec", "/v1/validate-spec", "/v1/convert"]
    for path in expected:
        assert f"'{path}'" in html or f'"{path}"' in html, f"missing fetch to {path}"


@pytest.mark.unit
def test_no_hardcoded_localhost_api(html: str) -> None:
    """Porta 8000 não deve aparecer no HTML (evita URL hardcoded)."""
    assert "localhost:8000" not in html


# ── Encoding repair ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_html_has_repair_mojibake_function(html: str) -> None:
    assert "_repairMojibake" in html


@pytest.mark.unit
def test_repair_mojibake_called_on_file_read(html: str) -> None:
    """_repairMojibake must be applied after reading specText from the FileReader."""
    idx_spectext = html.index("specText = _repairMojibake(")
    idx_def = html.index("function _repairMojibake(")
    assert idx_def < idx_spectext


# ── Stepper ───────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_has_stepper_nav(html: str) -> None:
    assert "stepper-nav" in html


@pytest.mark.unit
def test_has_four_step_panels(html: str) -> None:
    for n in ("1", "2", "3", "4"):
        assert f"step-panel-{n}" in html


@pytest.mark.unit
def test_has_step1_next_btn(html: str) -> None:
    assert "step1-next-btn" in html


@pytest.mark.unit
def test_has_verify_all_btn(html: str) -> None:
    assert "verify-all-btn" in html


@pytest.mark.unit
def test_has_verify_results_table(html: str) -> None:
    assert "verify-results-body" in html


# ── Aba URL ───────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_has_url_tab_panel(html: str) -> None:
    assert "tab-url" in html


@pytest.mark.unit
def test_has_fetch_url_btn(html: str) -> None:
    assert "fetch-url-btn" in html


@pytest.mark.unit
def test_fetch_url_endpoint_referenced(html: str) -> None:
    assert "'/v1/fetch-url'" in html or '"/v1/fetch-url"' in html


@pytest.mark.unit
def test_store_bundle_endpoint_referenced(html: str) -> None:
    assert "'/v1/store-bundle'" in html or '"/v1/store-bundle"' in html


@pytest.mark.unit
def test_verify_bundle_endpoint_referenced(html: str) -> None:
    assert "'/v1/verify-bundle'" in html or '"/v1/verify-bundle"' in html
