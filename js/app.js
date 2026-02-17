/**
 * Main UI logic for the Invoice Automation Tool frontend.
 */

// State
let poPdf = null;
let timesheetFiles = [];
let templateFile = null;
let lastResult = null;

// DOM elements
const poDropzone = document.getElementById("po-dropzone");
const poInput = document.getElementById("po-input");
const poFileList = document.getElementById("po-file-list");

const tsDropzone = document.getElementById("ts-dropzone");
const tsInput = document.getElementById("ts-input");
const tsFileList = document.getElementById("ts-file-list");

const tplDropzone = document.getElementById("tpl-dropzone");
const tplInput = document.getElementById("tpl-input");
const tplFileList = document.getElementById("tpl-file-list");

const configTextarea = document.getElementById("engineer-config");
const strictCheckbox = document.getElementById("strict-mode");
const generateBtn = document.getElementById("generate-btn");
const statusSection = document.getElementById("status-section");
const statusText = document.getElementById("status-text");
const resultsSection = document.getElementById("results-section");
const errorSection = document.getElementById("error-section");
const errorText = document.getElementById("error-text");
const healthDot = document.getElementById("health-dot");
const healthLabel = document.getElementById("health-label");

// --- Dropzone handlers ---

function setupDropzone(dropzone, input, onFiles) {
    dropzone.addEventListener("click", () => input.click());

    dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.classList.add("dragover");
    });

    dropzone.addEventListener("dragleave", () => {
        dropzone.classList.remove("dragover");
    });

    dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropzone.classList.remove("dragover");
        onFiles(e.dataTransfer.files);
    });

    input.addEventListener("change", () => {
        onFiles(input.files);
        input.value = "";
    });
}

function renderFileList(container, files, onRemove) {
    container.innerHTML = "";
    const arr = Array.isArray(files) ? files : [files];
    arr.forEach((f, i) => {
        if (!f) return;
        const div = document.createElement("div");
        div.className = "file-item";
        const size = f.size < 1024 * 1024
            ? `${(f.size / 1024).toFixed(1)} KB`
            : `${(f.size / (1024 * 1024)).toFixed(1)} MB`;
        div.innerHTML = `
            <span class="file-icon">&#128196;</span>
            <span class="file-name">${f.name}</span>
            <span class="file-size">${size}</span>
            <button class="file-remove" title="Remove">&times;</button>
        `;
        div.querySelector(".file-remove").addEventListener("click", (e) => {
            e.stopPropagation();
            onRemove(i);
        });
        container.appendChild(div);
    });
}

// PO PDF (single file)
setupDropzone(poDropzone, poInput, (files) => {
    if (files.length > 0) {
        poPdf = files[0];
        renderFileList(poFileList, [poPdf], () => {
            poPdf = null;
            renderFileList(poFileList, [], () => {});
            updateGenerateBtn();
        });
        updateGenerateBtn();
    }
});

// Timesheets (multiple files)
setupDropzone(tsDropzone, tsInput, (files) => {
    for (const f of files) {
        timesheetFiles.push(f);
    }
    renderFileList(tsFileList, timesheetFiles, (idx) => {
        timesheetFiles.splice(idx, 1);
        renderFileList(tsFileList, timesheetFiles, arguments.callee);
        updateGenerateBtn();
    });
    updateGenerateBtn();
});

// Template (single file)
setupDropzone(tplDropzone, tplInput, (files) => {
    if (files.length > 0) {
        templateFile = files[0];
        renderFileList(tplFileList, [templateFile], () => {
            templateFile = null;
            renderFileList(tplFileList, [], () => {});
            updateGenerateBtn();
        });
        updateGenerateBtn();
    }
});

// --- Button state ---

function updateGenerateBtn() {
    const ready = poPdf && timesheetFiles.length > 0 && templateFile;
    generateBtn.disabled = !ready;
}

// --- Generate ---

generateBtn.addEventListener("click", async () => {
    // Parse config
    let config;
    try {
        config = JSON.parse(configTextarea.value);
    } catch (e) {
        showError(`Invalid JSON config: ${e.message}`);
        return;
    }

    const strict = strictCheckbox.checked;

    // Show status
    statusSection.classList.remove("hidden");
    resultsSection.classList.add("hidden");
    errorSection.classList.add("hidden");
    statusText.textContent = "Processing... This may take 10-30 seconds.";
    generateBtn.disabled = true;

    try {
        const result = await generateInvoice(poPdf, timesheetFiles, templateFile, config, strict);
        lastResult = result;

        if (result.success) {
            showResults(result);
        } else {
            showError(result.errors?.join("\n") || "Unknown error");
        }
    } catch (e) {
        showError(`Request failed: ${e.message}`);
    } finally {
        statusSection.classList.add("hidden");
        updateGenerateBtn();
    }
});

// --- Results ---

function showResults(result) {
    resultsSection.classList.remove("hidden");
    errorSection.classList.add("hidden");

    // Grand total
    document.getElementById("grand-total").textContent =
        `$${result.summary.grand_total_usd.toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
    document.getElementById("contract-number").textContent = result.summary.contract_number;
    document.getElementById("total-hours").textContent = result.summary.total_hours.toFixed(0);
    document.getElementById("total-engineers").textContent = result.summary.total_engineers;

    // Hours breakdown
    document.getElementById("normal-hours").textContent = result.summary.total_normal_hours.toFixed(0);
    document.getElementById("ot-hours").textContent = result.summary.total_ot_hours.toFixed(0);
    document.getElementById("hot-hours").textContent = result.summary.total_hot_hours.toFixed(0);

    // Engineer cards
    const container = document.getElementById("engineer-cards");
    container.innerHTML = "";
    for (const eng of result.engineers) {
        const card = document.createElement("div");
        card.className = "engineer-card";
        card.innerHTML = `
            <div class="engineer-header" onclick="this.parentElement.classList.toggle('expanded')">
                <span class="arrow">&#9654;</span>
                <strong>${eng.name}</strong>
                <span class="tag ${eng.category}">${eng.category}</span>
                <span class="engineer-total">$${eng.total_cost.toLocaleString("en-US", { minimumFractionDigits: 2 })}</span>
            </div>
            <div class="engineer-details">
                <table>
                    <tr><th>Type</th><th>Hours</th><th>Rate</th><th>Cost</th></tr>
                    <tr>
                        <td>Normal</td>
                        <td>${eng.normal_hours}</td>
                        <td>$${eng.normal_rate.toFixed(2)}</td>
                        <td>$${eng.normal_cost.toLocaleString("en-US", { minimumFractionDigits: 2 })}</td>
                    </tr>
                    <tr>
                        <td>Overtime</td>
                        <td>${eng.ot_hours}</td>
                        <td>$${eng.ot_rate.toFixed(2)}</td>
                        <td>$${eng.ot_cost.toLocaleString("en-US", { minimumFractionDigits: 2 })}</td>
                    </tr>
                    <tr>
                        <td>HOT</td>
                        <td>${eng.hot_hours}</td>
                        <td>$${eng.hot_rate.toFixed(2)}</td>
                        <td>$${eng.hot_cost.toLocaleString("en-US", { minimumFractionDigits: 2 })}</td>
                    </tr>
                </table>
            </div>
        `;
        container.appendChild(card);
    }

    // Download buttons
    document.getElementById("dl-excel").onclick = () => {
        downloadBase64File(
            result.excel_base64,
            `Invoice_Report_${result.summary.contract_number}.xlsx`,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        );
    };

    document.getElementById("dl-audit").onclick = () => {
        downloadJson(result.audit, `Audit_${result.summary.contract_number}.json`);
    };
}

function showError(msg) {
    errorSection.classList.remove("hidden");
    resultsSection.classList.add("hidden");
    errorText.textContent = msg;
}

// --- Health check on load ---

async function checkBackendHealth() {
    const ok = await checkHealth();
    healthDot.className = `health-dot ${ok ? "healthy" : "unhealthy"}`;
    healthLabel.textContent = ok ? "API Connected" : "API Offline";
}

checkBackendHealth();
setInterval(checkBackendHealth, 30000);
