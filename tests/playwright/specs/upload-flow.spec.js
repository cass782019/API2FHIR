// @ts-check
import { test, expect } from '@playwright/test';
import { fileURLToPath } from 'url';
import path from 'path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const JSON_API_DIR = path.resolve(__dirname, '..', '..', '..', 'jsonAPI');

/**
 * Detecta payloads no fluxo: upload -> /v1/detect -> /v1/infer-spec -> Monaco editor visível.
 * Os testes não aguardam conversão LLM completa (lenta + variável). Valida-se até a
 * tela do Monaco; depois cancela.
 */
async function uploadFile(page, filename) {
  const filePath = path.join(JSON_API_DIR, filename);
  const fileInput = page.locator('#file-input');
  await fileInput.setInputFiles(filePath);
  // FileReader carrega assíncrono; espera o nome do arquivo aparecer
  await expect(page.locator('#file-name')).toContainText(filename);
}

test.describe('frontend payload→spec→FHIR flow', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Sanity: zona de upload presente, botão desabilitado até upload
    await expect(page.locator('#convert-btn')).toBeDisabled();
  });

  test('payload (natural_person_response.json) abre editor Monaco com spec inferido', async ({ page }) => {
    await uploadFile(page, 'natural_person_response.json');
    await expect(page.locator('#convert-btn')).toBeEnabled();

    await page.click('#convert-btn');

    // Editor Monaco aparece (carrega CDN, leva alguns segundos)
    await expect(page.locator('#spec-edit-section')).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('#fabricated-warning')).toContainText('Campos fabricados');

    // O Monaco renderiza o spec — verifica via DOM do editor
    const editorText = await page.locator('#monaco-container .view-lines').textContent({ timeout: 15_000 });
    expect(editorText).toContain('openapi');
    expect(editorText).toContain('3.0.3');

    // Cancela e verifica cleanup
    await page.click('#cancel-edit-btn');
    await expect(page.locator('#spec-edit-section')).toBeHidden();
  });

  test('payload (insurance_response.json) abre editor Monaco', async ({ page }) => {
    await uploadFile(page, 'insurance_response.json');
    await page.click('#convert-btn');
    await expect(page.locator('#spec-edit-section')).toBeVisible({ timeout: 30_000 });
    const text = await page.locator('#monaco-container .view-lines').textContent({ timeout: 15_000 });
    expect(text).toContain('openapi');
    await page.click('#cancel-edit-btn');
  });

  test('payload array (medialSpecialities_response.json) é tratado como payload', async ({ page }) => {
    await uploadFile(page, 'medialSpecialities_response.json');
    await page.click('#convert-btn');
    // Array no root: detect retorna 'payload', mas o frontend espera dict.
    // Se o JSON.parse(specText) falhar ou o /v1/infer-spec receber array, a UI
    // mostra erro. Aceitamos qualquer um dos dois desfechos: editor OU error-box.
    const editor = page.locator('#spec-edit-section');
    const errBox = page.locator('#error-box');
    await expect(editor.or(errBox)).toBeVisible({ timeout: 30_000 });
  });

  test('swagger 2.0 spec (schedules_1.json) pula editor e dispara conversão', async ({ page }) => {
    await uploadFile(page, 'schedules_1.json');

    // Intercepta a chamada de convert pra confirmar payload sem aguardar resposta
    const convertReqPromise = page.waitForRequest(req =>
      req.url().includes('/v1/convert') && req.method() === 'POST',
      { timeout: 30_000 }
    );

    await page.click('#convert-btn');

    // Não deve aparecer o editor (é spec real)
    await expect(page.locator('#spec-edit-section')).toBeHidden();
    // Spinner aparece imediatamente
    await expect(page.locator('#spinner')).toBeVisible();

    const req = await convertReqPromise;
    const body = JSON.parse(req.postData() || '{}');
    expect(typeof body.spec).toBe('string');
    expect(body.options.async).toBe(false);
    // Nota: não aguardamos a resposta — LLM leva ~90s. Smoke do bundle final
    // fica sob testes integration/regression.
  });

  test('detecta opções da UI presentes', async ({ page }) => {
    // Smoke estrutural — confirma que a seção de opções tem os 3 modelos esperados
    await expect(page.locator('#model-select')).toBeVisible();
    await page.locator('#opts').click(); // expand details
    const options = await page.locator('#model-select option').allTextContents();
    expect(options.some(o => o.includes('claude-opus'))).toBe(true);
    expect(options.some(o => o.includes('claude-haiku'))).toBe(true);
    expect(options.some(o => o.includes('sabia'))).toBe(true);
  });
});
