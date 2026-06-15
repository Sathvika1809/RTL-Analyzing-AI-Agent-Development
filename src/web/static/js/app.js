// Global State
let activeFile = null;
let originalCode = "";
let currentCode = "";
let analysisResults = null;

// DOM Elements
const modelSelect = document.getElementById("model-select");
const filesContainer = document.getElementById("files-container");
const lblFileCount = document.getElementById("lbl-file-count");
const lblActiveFile = document.getElementById("lbl-active-file");
const lblSaveStatus = document.getElementById("lbl-save-status");
const codeEditor = document.getElementById("code-editor");

const btnRefresh = document.getElementById("btn-refresh");
const btnSave = document.getElementById("btn-save");
const btnAnalyze = document.getElementById("btn-analyze");
const btnAutoFix = document.getElementById("btn-auto-fix");
const btnCopyAssertions = document.getElementById("btn-copy-assertions");

const btnCreateFile = document.getElementById("btn-create-file");
const btnDeleteFile = document.getElementById("btn-delete-file");
const chkParallel = document.getElementById("chk-parallel");
const errorBanner = document.getElementById("error-banner");
const btnCloseError = document.getElementById("btn-close-error");

// Chat Elements
const chatInput = document.getElementById("chat-input");
const btnSendChat = document.getElementById("btn-send-chat");
const chatMessages = document.getElementById("chat-messages");

// Progress elements
const overlayProgress = document.getElementById("overlay-progress");
const lblProgressTitle = document.getElementById("lbl-progress-title");
const lblProgressSubtitle = document.getElementById("lbl-progress-subtitle");
const progressFill = document.getElementById("progress-fill");

// Modal elements
const modalFix = document.getElementById("modal-fix");
const lblFixExplanation = document.getElementById("lbl-fix-explanation");
const btnCloseModal = document.getElementById("btn-close-modal");
const btnCancelFix = document.getElementById("btn-cancel-fix");
const btnApplyFix = document.getElementById("btn-apply-fix");

// Tabs badges & panels
const tabBadges = {
    bugs: document.getElementById("badge-bugs"),
    timing: document.getElementById("badge-timing"),
    assertions: document.getElementById("badge-assertions"),
    opts: document.getElementById("badge-opts")
};

const tabMetrics = {
    bugSeverity: document.getElementById("val-bug-severity"),
    timingRisk: document.getElementById("val-timing-risk"),
    assertionCoverage: document.getElementById("val-assertion-coverage"),
    optsQuality: document.getElementById("val-opts-quality")
};

const tabFindings = {
    bugs: document.getElementById("bugs-findings"),
    timing: document.getElementById("timing-findings"),
    assertions: document.getElementById("assertions-findings"),
    opts: document.getElementById("opts-findings")
};

// Initialization
document.addEventListener("DOMContentLoaded", () => {
    initApp();
    setupEvents();
});

async function initApp() {
    showOverlayProgress("Initializing Workspace", "Fetching models, server status, and RTL modules...");
    await Promise.all([checkOllamaStatus(), loadModels(), loadFiles()]);
    hideOverlayProgress();
}

function setupEvents() {
    // Refresh files/models
    btnRefresh.addEventListener("click", initApp);
    
    // Save file
    btnSave.addEventListener("click", saveFile);
    
    // Run analysis
    btnAnalyze.addEventListener("click", runAnalysis);
    
    // Run auto fix
    btnAutoFix.addEventListener("click", runAutoFix);
    
    // Copy SVA
    btnCopyAssertions.addEventListener("click", copyAssertions);

    // Create file
    btnCreateFile.addEventListener("click", createFile);

    // Delete file
    btnDeleteFile.addEventListener("click", deleteFile);

    // Error banner close
    btnCloseError.addEventListener("click", () => {
        errorBanner.style.display = "none";
    });

    // Chat sending
    btnSendChat.addEventListener("click", sendCustomChat);
    chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            sendCustomChat();
        }
    });
    
    // Editor typing tracking
    codeEditor.addEventListener("input", (e) => {
        currentCode = e.target.value;
        if (currentCode !== originalCode) {
            lblSaveStatus.textContent = "Unsaved Changes";
            lblSaveStatus.className = "save-status unsaved";
            btnSave.disabled = false;
        } else {
            lblSaveStatus.textContent = "Saved";
            lblSaveStatus.className = "save-status";
            btnSave.disabled = true;
        }
    });

    // Tab switcher
    document.querySelectorAll(".tab-link").forEach(link => {
        link.addEventListener("click", (e) => {
            document.querySelectorAll(".tab-link").forEach(t => t.classList.remove("active"));
            document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
            
            const targetLink = e.currentTarget;
            targetLink.classList.add("active");
            
            const tabId = targetLink.getAttribute("data-tab");
            document.getElementById(tabId).classList.add("active");
        });
    });

    // Modal closing
    btnCloseModal.addEventListener("click", () => modalFix.classList.remove("active"));
    btnCancelFix.addEventListener("click", () => modalFix.classList.remove("active"));
    btnApplyFix.addEventListener("click", applyFix);
}

// Check if Ollama service is reachable
async function checkOllamaStatus() {
    const badge = document.getElementById("ollama-status");
    try {
        const resp = await fetch("/api/models");
        const data = await resp.json();
        if (data.success) {
            badge.className = "status-badge online animate-fade-in";
            badge.innerHTML = '<span class="status-dot"></span> Ollama: Online';
        } else {
            badge.className = "status-badge offline animate-fade-in";
            badge.innerHTML = '<span class="status-dot"></span> Ollama: Offline';
        }
    } catch (err) {
        badge.className = "status-badge offline animate-fade-in";
        badge.innerHTML = '<span class="status-dot"></span> Ollama: Offline';
    }
}

// Fetch models list from Ollama backend
async function loadModels() {
    try {
        const resp = await fetch("/api/models");
        const data = await resp.json();
        
        modelSelect.innerHTML = "";
        
        if (data.success && data.models.length > 0) {
            data.models.forEach(model => {
                const opt = document.createElement("option");
                opt.value = model;
                opt.textContent = model;
                modelSelect.appendChild(opt);
            });
            
            // Set qwen2.5:3b or first model as default
            const hasQwen = data.models.includes("qwen2.5:3b");
            if (hasQwen) {
                modelSelect.value = "qwen2.5:3b";
            } else {
                modelSelect.value = data.models[0];
            }
        } else {
            const opt = document.createElement("option");
            opt.value = "";
            opt.textContent = "No models found (Ollama offline?)";
            modelSelect.appendChild(opt);
        }
    } catch (err) {
        console.error("Error fetching models:", err);
    }
}

// Fetch SV files list from backend
async function loadFiles() {
    try {
        const resp = await fetch("/api/files");
        const data = await resp.json();
        
        filesContainer.innerHTML = "";
        
        if (data.success && data.files.length > 0) {
            lblFileCount.textContent = `${data.files.length} modules`;
            
            data.files.forEach(filename => {
                const div = document.createElement("div");
                div.className = "file-item animate-fade-in";
                const ext = filename.split(".").pop().toUpperCase();
                div.innerHTML = `
                    <div class="file-item-left">
                        <i class="fa-solid fa-microchip"></i>
                        <span class="file-name" title="${filename}">${filename}</span>
                    </div>
                    <span class="file-badge">${ext}</span>
                `;
                
                div.addEventListener("click", () => selectFile(filename, div));
                filesContainer.appendChild(div);
            });
        } else {
            lblFileCount.textContent = "0 modules";
            filesContainer.innerHTML = `<div class="empty-state"><p>No .sv or .v files found in rtl_files/</p></div>`;
        }
    } catch (err) {
        console.error("Error fetching files:", err);
    }
}

// Create a new module in files list
async function createFile() {
    const filename = prompt("Enter new filename (must end with .sv or .v):");
    if (!filename) return;
    
    if (!filename.endsWith(".sv") && !filename.endsWith(".v")) {
        alert("Error: Filename must end with .sv or .v");
        return;
    }
    
    const moduleName = filename.split(".")[0];
    const template = `// Module: ${moduleName}\nmodule ${moduleName} (\n    input  logic clk,\n    input  logic rst_n\n);\n\n    // Write your HDL code here...\n\nendmodule\n`;
    
    showOverlayProgress("Creating Module", `Writing ${filename}...`);
    try {
        const resp = await fetch("/api/file/create", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ filename, code: template })
        });
        const data = await resp.json();
        if (data.success) {
            await loadFiles();
            alert(`Created ${filename} successfully.`);
        } else {
            alert(`Error: ${data.detail}`);
        }
    } catch (err) {
        console.error("Error creating file:", err);
        alert("Failed to create file.");
    } finally {
        hideOverlayProgress();
    }
}

// Delete selected module
async function deleteFile() {
    if (!activeFile) return;
    
    if (!confirm(`Are you sure you want to delete ${activeFile}? This action is irreversible.`)) {
        return;
    }
    
    showOverlayProgress("Deleting Module", `Removing ${activeFile}...`);
    try {
        const resp = await fetch(`/api/file/${activeFile}`, {
            method: "DELETE"
        });
        const data = await resp.json();
        if (data.success) {
            activeFile = null;
            originalCode = "";
            currentCode = "";
            codeEditor.value = "";
            codeEditor.placeholder = "// Select a file from the sidebar to view/edit RTL code...";
            lblActiveFile.textContent = "No file selected";
            btnSave.disabled = true;
            btnAnalyze.disabled = true;
            btnDeleteFile.disabled = true;
            
            clearResults();
            await loadFiles();
            alert("Deleted successfully.");
        } else {
            alert(`Failed to delete: ${data.detail}`);
        }
    } catch (err) {
        console.error("Delete file error:", err);
        alert("Failed to delete file.");
    } finally {
        hideOverlayProgress();
    }
}

// Select file and fetch content
async function selectFile(filename, element) {
    // UI update for selected class
    document.querySelectorAll(".file-item").forEach(item => item.classList.remove("active"));
    element.classList.add("active");
    
    showOverlayProgress("Opening File", `Loading ${filename}...`);
    
    try {
        const resp = await fetch(`/api/file/${filename}`);
        const data = await resp.json();
        
        if (data.success) {
            activeFile = filename;
            originalCode = data.content;
            currentCode = data.content;
            
            codeEditor.value = data.content;
            lblActiveFile.textContent = filename;
            
            lblSaveStatus.textContent = "Saved";
            lblSaveStatus.className = "save-status";
            
            btnSave.disabled = true;
            btnAnalyze.disabled = false;
            btnDeleteFile.disabled = false;
            
            // Enable and reset Custom Chat input
            chatInput.disabled = false;
            btnSendChat.disabled = false;
            chatMessages.innerHTML = `
                <div class="chat-bubble agent animate-zoom-in">
                    <p>Hello! I am RTL-Agent. Ask me any question or give me an instruction regarding <strong>${filename}</strong>. For example: "Explain the reset logic" or "Check if it can cause latches."</p>
                </div>
            `;
            
            // Clear prior results dashboard
            clearResults();
        } else {
            alert(`Error: ${data.detail}`);
        }
    } catch (err) {
        console.error("Error reading file:", err);
    } finally {
        hideOverlayProgress();
    }
}

// Save Editor Content back to Server
async function saveFile() {
    if (!activeFile) return;
    
    showOverlayProgress("Saving Module", `Writing code changes back to ${activeFile}...`);
    try {
        const resp = await fetch(`/api/file/${activeFile}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ code: currentCode })
        });
        const data = await resp.json();
        
        if (data.success) {
            originalCode = currentCode;
            lblSaveStatus.textContent = "Saved";
            lblSaveStatus.className = "save-status";
            btnSave.disabled = true;
        } else {
            alert("Failed to save changes.");
        }
    } catch (err) {
        console.error("Save error:", err);
    } finally {
        hideOverlayProgress();
    }
}

// Trigger parallel multi-agent analysis on active file
async function runAnalysis() {
    if (!activeFile) return;
    
    const model = modelSelect.value;
    if (!model) {
        alert("Please select a local Ollama model first.");
        return;
    }
    
    const parallel = chkParallel.checked;
    
    showOverlayProgress(
        "Analyzing SystemVerilog",
        `Executing agents in ${parallel ? 'parallel' : 'sequential'} mode using model '${model}'... This can take up to 2 minutes.`
    );
    
    try {
        const resp = await fetch("/api/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ filename: activeFile, model: model, parallel: parallel })
        });
        const data = await resp.json();
        
        if (data.success) {
            analysisResults = data.results;
            completePipeline(data.results);
            renderAnalysisResults(data.results);
        } else {
            failPipeline();
            alert(`Analysis failed: ${data.detail}`);
        }
    } catch (err) {
        console.error("Analysis error:", err);
        failPipeline();
        alert("Verification check failed to complete.");
    } finally {
        setTimeout(() => {
            hideOverlayProgress();
        }, 1200);
    }
}

// Send custom chat query to CustomAgent
async function sendCustomChat() {
    const query = chatInput.value.trim();
    if (!query || !activeFile) return;
    
    const model = modelSelect.value;
    if (!model) {
        alert("Please select a model first.");
        return;
    }
    
    // Add User Bubble
    const userBubble = document.createElement("div");
    userBubble.className = "chat-bubble user animate-zoom-in";
    userBubble.innerHTML = `<p>${escapeHtml(query)}</p>`;
    chatMessages.appendChild(userBubble);
    chatInput.value = "";
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    // Add Typing bubble
    const typingBubble = document.createElement("div");
    typingBubble.className = "chat-bubble agent typing animate-zoom-in";
    typingBubble.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> RTL-Agent is thinking...`;
    chatMessages.appendChild(typingBubble);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    try {
        const resp = await fetch("/api/custom-query", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ filename: activeFile, model: model, query: query })
        });
        const data = await resp.json();
        
        chatMessages.removeChild(typingBubble);
        
        const agentBubble = document.createElement("div");
        agentBubble.className = "chat-bubble agent animate-zoom-in";
        
        if (data.success) {
            agentBubble.innerHTML = `<div class="markdown-body">${formatMarkdown(data.response)}</div>`;
        } else {
            agentBubble.innerHTML = `<p class="text-red">Error: ${escapeHtml(data.detail)}</p>`;
        }
        chatMessages.appendChild(agentBubble);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    } catch (err) {
        console.error("Chat error:", err);
        if (typingBubble.parentNode) {
            chatMessages.removeChild(typingBubble);
        }
        const errBubble = document.createElement("div");
        errBubble.className = "chat-bubble agent animate-zoom-in";
        errBubble.innerHTML = `<p class="text-red">Error: Connection lost or request timed out.</p>`;
        chatMessages.appendChild(errBubble);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
}

// Simple Markdown Formatter
function formatMarkdown(text) {
    if (!text) return "";
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/```systemverilog([\s\S]*?)```/g, '<pre class="code-pre"><code>$1</code></pre>')
        .replace(/```verilog([\s\S]*?)```/g, '<pre class="code-pre"><code>$1</code></pre>')
        .replace(/```json([\s\S]*?)```/g, '<pre class="code-pre"><code>$1</code></pre>')
        .replace(/```([\s\S]*?)```/g, '<pre class="code-pre"><code>$1</code></pre>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/^\s*-\s+(.+)$/gm, '<li>$1</li>')
        .replace(/(<li>.*<\/li>)/g, '<ul>$1</ul>')
        .replace(/\n/g, '<br>');
}

// Clear dashboard data
function clearResults() {
    analysisResults = null;
    btnAutoFix.disabled = true;
    btnCopyAssertions.disabled = true;
    errorBanner.style.display = "none";
    
    // Reset badges
    tabBadges.bugs.textContent = "0";
    tabBadges.timing.textContent = "0";
    tabBadges.assertions.textContent = "0";
    tabBadges.opts.textContent = "0";
    
    // Reset metrics
    tabMetrics.bugSeverity.textContent = "-";
    tabMetrics.bugSeverity.className = "metric-val";
    tabMetrics.timingRisk.textContent = "-";
    tabMetrics.timingRisk.className = "metric-val";
    tabMetrics.assertionCoverage.textContent = "-";
    tabMetrics.assertionCoverage.className = "metric-val";
    tabMetrics.optsQuality.textContent = "-";
    tabMetrics.optsQuality.className = "metric-val";
    
    // Reset panels
    tabFindings.bugs.innerHTML = `<div class="empty-state"><i class="fa-solid fa-circle-check"></i><p>No analysis run yet. Select a file and click "Run Multi-Agent Analysis".</p></div>`;
    tabFindings.timing.innerHTML = `<div class="empty-state"><i class="fa-solid fa-clock"></i><p>Select a file and trigger analysis to check CDC, latches, and clock properties.</p></div>`;
    tabFindings.assertions.innerHTML = `<div class="empty-state"><i class="fa-solid fa-shield"></i><p>Assertions generated by LLM based on RTL logic will appear here.</p></div>`;
    tabFindings.opts.innerHTML = `<div class="empty-state"><i class="fa-solid fa-lightbulb"></i><p>Style, naming conventions, and parameter recommendations will be displayed here.</p></div>`;
}

// Render Analysis Output in UI
function renderAnalysisResults(res) {
    // Check for warnings and display error banner
    const errors = [];
    if (res.bug_error) errors.push(`BugAgent: ${res.bug_error}`);
    if (res.timing_error) errors.push(`TimingAgent: ${res.timing_error}`);
    if (res.assertion_error) errors.push(`AssertionAgent: ${res.assertion_error}`);
    if (res.optimization_error) errors.push(`OptimizerAgent: ${res.optimization_error}`);
    
    if (errors.length > 0) {
        errorBanner.querySelector("#error-banner-text").innerHTML = "<strong>Some Agents Failed:</strong><br>" + errors.join("<br>");
        errorBanner.style.display = "flex";
    } else {
        errorBanner.style.display = "none";
    }

    // 1. Bugs Tab
    tabBadges.bugs.textContent = res.total_bugs;
    tabMetrics.bugSeverity.textContent = res.severity;
    tabMetrics.bugSeverity.className = `metric-val text-${res.severity === 'CRITICAL' || res.severity === 'HIGH' ? 'red' : res.severity === 'MEDIUM' ? 'yellow' : 'green'}`;
    
    if (res.bugs && res.bugs.length > 0) {
        tabFindings.bugs.innerHTML = "";
        res.bugs.forEach(bug => {
            const card = document.createElement("div");
            card.className = "finding-card animate-zoom-in";
            card.innerHTML = `
                <div class="card-top">
                    <span class="finding-tag ${bug.type ? bug.type.toLowerCase() : 'functional'}">${bug.type || 'BUG'}</span>
                    <span class="finding-location">${escapeHtml(bug.location)}</span>
                </div>
                <div class="finding-problem"><strong>Problem:</strong> ${escapeHtml(bug.problem)}</div>
                <div class="finding-impact"><strong>Consequence:</strong> ${escapeHtml(bug.impact)}</div>
                <div class="finding-fix"><strong>Suggested Fix:</strong>\n${escapeHtml(bug.fix)}</div>
            `;
            tabFindings.bugs.appendChild(card);
        });
        btnAutoFix.disabled = false;
    } else {
        tabFindings.bugs.innerHTML = `
            <div class="empty-state text-green">
                <i class="fa-solid fa-circle-check"></i>
                <p>No bugs, latches, or reset anomalies detected by BugAgent.</p>
            </div>
        `;
    }

    // 2. Timing Tab
    tabBadges.timing.textContent = res.total_timing_issues;
    tabMetrics.timingRisk.textContent = res.risk;
    tabMetrics.timingRisk.className = `metric-val text-${res.risk === 'HIGH' ? 'red' : res.risk === 'MEDIUM' ? 'yellow' : 'green'}`;
    
    if (res.timing_issues && res.timing_issues.length > 0) {
        tabFindings.timing.innerHTML = "";
        res.timing_issues.forEach(issue => {
            const card = document.createElement("div");
            card.className = "finding-card animate-zoom-in";
            card.innerHTML = `
                <div class="card-top">
                    <span class="finding-tag ${issue.type ? issue.type.toLowerCase() : 'cdc'}">${issue.type || 'TIMING'}</span>
                    <span class="finding-location">${escapeHtml(issue.location)}</span>
                </div>
                <div class="finding-problem"><strong>Problem:</strong> ${escapeHtml(issue.problem)}</div>
                <div class="finding-impact"><strong>Silicon Risk:</strong> ${escapeHtml(issue.risk)}</div>
                <div class="finding-fix"><strong>Suggested Fix:</strong>\n${escapeHtml(issue.fix)}</div>
            `;
            tabFindings.timing.appendChild(card);
        });
        btnAutoFix.disabled = false;
    } else {
        tabFindings.timing.innerHTML = `
            <div class="empty-state text-green">
                <i class="fa-solid fa-clock"></i>
                <p>No timing hazards, clock domain crossing, or sequential blocking assignments detected.</p>
            </div>
        `;
    }

    // 3. Assertions Tab
    tabBadges.assertions.textContent = res.total_assertions;
    tabMetrics.assertionCoverage.textContent = res.coverage;
    tabMetrics.assertionCoverage.className = `metric-val text-${res.coverage === 'HIGH' ? 'green' : res.coverage === 'MEDIUM' ? 'blue' : 'yellow'}`;
    
    if (res.assertions && res.assertions.length > 0) {
        tabFindings.assertions.innerHTML = "";
        res.assertions.forEach(assert => {
            const div = document.createElement("div");
            div.className = "assertion-item animate-zoom-in";
            div.innerHTML = `
                <div class="assertion-header">
                    <span class="assertion-title"><i class="fa-solid fa-shield-halved text-blue"></i> ${assert.type} Property (Target: ${escapeHtml(assert.signal)})</span>
                </div>
                <div class="assertion-desc">${escapeHtml(assert.description)}</div>
                <pre class="assertion-code">${escapeHtml(assert.sva_code)}</pre>
            `;
            tabFindings.assertions.appendChild(div);
        });
        btnCopyAssertions.disabled = false;
    } else {
        tabFindings.assertions.innerHTML = `
            <div class="empty-state">
                <i class="fa-solid fa-shield"></i>
                <p>No SVA assertions could be generated from the given modules.</p>
            </div>
        `;
    }

    // 4. Optimizations Tab
    tabBadges.opts.textContent = res.total_optimizations;
    tabMetrics.optsQuality.textContent = res.quality_score;
    tabMetrics.optsQuality.className = `metric-val text-${res.quality_score === 'HIGH' ? 'green' : res.quality_score === 'MEDIUM' ? 'yellow' : 'red'}`;
    
    if (res.optimizations && res.optimizations.length > 0) {
        tabFindings.opts.innerHTML = "";
        res.optimizations.forEach(opt => {
            const card = document.createElement("div");
            card.className = "finding-card animate-zoom-in";
            card.innerHTML = `
                <div class="card-top">
                    <span class="finding-tag ${opt.type ? opt.type.toLowerCase() : 'style'}">${opt.type || 'OPTIMIZATION'}</span>
                    <span class="finding-location">${escapeHtml(opt.location)}</span>
                </div>
                <div class="finding-problem"><strong>Improvement Opportunity:</strong> ${escapeHtml(opt.issue)}</div>
                <div class="finding-impact"><strong>PPA / Quality Benefit:</strong> ${escapeHtml(opt.benefit)}</div>
                <div class="finding-fix"><strong>Refactoring Recommendation:</strong>\n${escapeHtml(opt.suggestion)}</div>
            `;
            tabFindings.opts.appendChild(card);
        });
        btnAutoFix.disabled = false;
    } else {
        tabFindings.opts.innerHTML = `
            <div class="empty-state text-green">
                <i class="fa-solid fa-circle-check"></i>
                <p>Code quality score is high. No optimization opportunities suggested.</p>
            </div>
        `;
    }
}

// Trigger Auto Fix LLM Agent
let fixedCodeProposed = "";
async function runAutoFix() {
    if (!activeFile || !analysisResults) return;
    
    const model = modelSelect.value;
    
    showOverlayProgress("Generating Automatic Repair", "FixerAgent refactoring SystemVerilog code to resolve issues...");
    
    try {
        const resp = await fetch("/api/fix", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                filename: activeFile,
                model: model,
                bugs: analysisResults.bugs,
                timing_issues: analysisResults.timing_issues,
                optimizations: analysisResults.optimizations
            })
        });
        const data = await resp.json();
        
        if (data.success) {
            fixedCodeProposed = data.fixed_code;
            lblFixExplanation.textContent = `Applied repairs: ${data.explanation} (Generated in ${data.elapsed_s}s)`;
            
            // Render diff view
            renderDiff(currentCode, fixedCodeProposed);
            
            // Display modal
            modalFix.classList.add("active");
        } else {
            alert(`Auto-fix error: ${data.detail}`);
        }
    } catch (err) {
        console.error("Auto fix request failed:", err);
        alert("Failed to run Auto-Fix refactoring.");
    } finally {
        hideOverlayProgress();
    }
}

// Render Side by side visual code comparison
function renderDiff(original, fixed) {
    const origLines = original.split("\n");
    const fixedLines = fixed.split("\n");
    
    let origHtml = "";
    let fixedHtml = "";
    
    const maxLines = Math.max(origLines.length, fixedLines.length);
    for (let i = 0; i < maxLines; i++) {
        const origLine = origLines[i] !== undefined ? origLines[i] : "";
        const fixedLine = fixedLines[i] !== undefined ? fixedLines[i] : "";
        
        if (origLine === fixedLine) {
            origHtml += `<div>${escapeHtml(origLine)}</div>`;
            fixedHtml += `<div>${escapeHtml(fixedLine)}</div>`;
        } else {
            if (origLines[i] !== undefined) {
                origHtml += `<div class="diff-removed">- ${escapeHtml(origLine)}</div>`;
            } else {
                origHtml += `<div></div>`;
            }
            if (fixedLines[i] !== undefined) {
                fixedHtml += `<div class="diff-added">+ ${escapeHtml(fixedLine)}</div>`;
            } else {
                fixedHtml += `<div></div>`;
            }
        }
    }
    document.getElementById("diff-original-code").innerHTML = origHtml;
    document.getElementById("diff-fixed-code").innerHTML = fixedHtml;
}

// Write the fixed code to active editor and save file
async function applyFix() {
    if (!activeFile || !fixedCodeProposed) return;
    
    currentCode = fixedCodeProposed;
    codeEditor.value = fixedCodeProposed;
    
    modalFix.classList.remove("active");
    
    lblSaveStatus.textContent = "Unsaved Changes";
    lblSaveStatus.className = "save-status unsaved";
    
    // Save to server
    await saveFile();
    
    // Clear and rerun analysis
    clearResults();
    alert("Repairs applied and saved! Run analysis again to verify module correctness.");
}

// Copy assertions to clipboard
function copyAssertions() {
    if (!analysisResults || analysisResults.assertions.length === 0) return;
    
    const assertionsText = analysisResults.assertions.map(assert => {
        return `// ${assert.type}: ${assert.description}\n${assert.sva_code}`;
    }).join("\n\n");
    
    navigator.clipboard.writeText(assertionsText)
        .then(() => alert("SVA properties copied to clipboard!"))
        .catch(err => console.error("Clipboard copy failure:", err));
}

let pipelineInterval = null;

function startPipelineAnimation(isParallel) {
    const nodes = ['bug', 'timing', 'assertion', 'optimizer'];
    nodes.forEach(name => {
        const node = document.getElementById(`node-${name}`);
        const status = document.getElementById(`status-${name}`);
        if (node && status) {
            node.className = "pipeline-node";
            status.textContent = "Pending";
        }
    });

    const pipelineFlow = document.getElementById("pipeline-flow");
    if (pipelineFlow) pipelineFlow.style.display = "flex";

    if (isParallel) {
        nodes.forEach(name => {
            const node = document.getElementById(`node-${name}`);
            const status = document.getElementById(`status-${name}`);
            if (node && status) {
                node.classList.add("running");
                status.textContent = "Running...";
            }
        });
    } else {
        let currentStep = 0;
        const steps = [
            { name: 'bug', duration: 40 },
            { name: 'timing', duration: 45 },
            { name: 'assertion', duration: 45 },
            { name: 'optimizer', duration: 40 }
        ];

        const runStep = () => {
            if (currentStep > 0) {
                const prevName = steps[currentStep - 1].name;
                const prevNode = document.getElementById(`node-${prevName}`);
                const prevStatus = document.getElementById(`status-${prevName}`);
                if (prevNode && prevStatus) {
                    prevNode.classList.remove("running");
                    prevNode.classList.add("completed");
                    prevStatus.textContent = "Completed";
                }
            }

            if (currentStep < steps.length) {
                const name = steps[currentStep].name;
                const node = document.getElementById(`node-${name}`);
                const status = document.getElementById(`status-${name}`);
                if (node && status) {
                    node.classList.add("running");
                    status.textContent = "Running...";
                }
                
                const timeout = steps[currentStep].duration * 1000;
                pipelineInterval = setTimeout(() => {
                    currentStep++;
                    runStep();
                }, timeout);
            }
        };

        runStep();
    }
}

function completePipeline(results) {
    if (pipelineInterval) {
        clearTimeout(pipelineInterval);
        pipelineInterval = null;
    }

    const nodes = [
        { name: 'bug', errKey: 'bug_error' },
        { name: 'timing', errKey: 'timing_error' },
        { name: 'assertion', errKey: 'assertion_error' },
        { name: 'optimizer', errKey: 'optimization_error' }
    ];

    nodes.forEach(nodeInfo => {
        const node = document.getElementById(`node-${nodeInfo.name}`);
        const status = document.getElementById(`status-${nodeInfo.name}`);
        if (node && status) {
            node.className = "pipeline-node";
            if (results && results[nodeInfo.errKey]) {
                node.classList.add("failed");
                status.textContent = "Failed";
            } else {
                node.classList.add("completed");
                status.textContent = "Completed";
            }
        }
    });
}

function failPipeline() {
    if (pipelineInterval) {
        clearTimeout(pipelineInterval);
        pipelineInterval = null;
    }
    const nodes = ['bug', 'timing', 'assertion', 'optimizer'];
    nodes.forEach(name => {
        const node = document.getElementById(`node-${name}`);
        const status = document.getElementById(`status-${name}`);
        if (node && status && !node.classList.contains("completed")) {
            node.className = "pipeline-node failed";
            status.textContent = "Failed";
        }
    });
}

// Overlay utility controls
function showOverlayProgress(title, subtitle) {
    lblProgressTitle.textContent = title;
    lblProgressSubtitle.textContent = subtitle;
    progressFill.style.width = "0%";
    overlayProgress.classList.add("active");
    
    const pipelineFlow = document.getElementById("pipeline-flow");
    if (title === "Analyzing SystemVerilog") {
        startPipelineAnimation(chkParallel.checked);
    } else {
        if (pipelineFlow) pipelineFlow.style.display = "none";
    }

    // Start an artificial slow fill animation
    setTimeout(() => {
        progressFill.style.width = "90%";
    }, 100);
}

function hideOverlayProgress() {
    progressFill.style.width = "100%";
    setTimeout(() => {
        overlayProgress.classList.remove("active");
        const pipelineFlow = document.getElementById("pipeline-flow");
        if (pipelineFlow) pipelineFlow.style.display = "none";
    }, 400);
}

// Utility: HTML Sanitizer
function escapeHtml(text) {
    if (typeof text !== "string") return "";
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
