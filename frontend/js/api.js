/**
 * API communication layer for the Invoice Automation Tool.
 */

async function generateInvoice(poPdf, timesheets, template, engineerConfig, strict) {
    const formData = new FormData();
    formData.append("po_pdf", poPdf);
    for (const ts of timesheets) {
        formData.append("timesheets", ts);
    }
    formData.append("template", template);
    formData.append("engineer_config", JSON.stringify(engineerConfig));
    formData.append("strict", strict.toString());

    const response = await fetch(`${CONFIG.API_BASE_URL}/api/v1/generate`, {
        method: "POST",
        body: formData,
    });

    if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
            const err = await response.json();
            detail = err.detail || err.errors?.join("\n") || detail;
        } catch { /* ignore parse errors */ }
        throw new Error(detail);
    }

    return await response.json();
}

async function checkHealth() {
    try {
        const res = await fetch(`${CONFIG.API_BASE_URL}/api/v1/health`);
        return res.ok;
    } catch {
        return false;
    }
}
