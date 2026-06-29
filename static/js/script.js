// Client-side orchestrator for UI state, file ingestion, and API communication.
document.addEventListener('DOMContentLoaded', () => {
    'use strict';

    // Global reference for the currently staged file stream.
    let uploadedFileStream = null;
    let primaryAudioContext = null;

    // DOM node cache to optimize selector performance and memory management.
    const DOMNodes = {
        dropZone: document.getElementById('image-drop-zone'),
        fileInput: document.getElementById('image-file-input'),
        previewFrame: document.getElementById('image-preview-frame'),
        inferenceBtn: document.getElementById('execute-inference-btn'),
        dashboardView: document.getElementById('dashboard-core-view'),
        authView: document.getElementById('restricted-auth-view'),
        featuresView: document.getElementById('page-features'),
        helpView: document.getElementById('page-help'),
        captionOutput: document.getElementById('caption-output-text'),
        copyCaptionBtn: document.getElementById('copy-caption-btn'),
        backboneModelMeta: document.getElementById('backbone-model-meta'),
        confidenceScore: document.getElementById('model-confidence-score'),
        historyStreamTarget: document.getElementById('history-stream-target'),
        refreshHistoryBtn: document.getElementById('refresh-history-btn'),
        toastContainer: document.getElementById('global-toast-container-anchor'),
        helpSearchInput: document.getElementById('help-search-input'),
        faqItems: document.querySelectorAll('.faq-item')
    };

    // Section: Navigation and Modal Management

    // Global authentication state tracker.
    window.isUserAuthenticated = false;

    window.navigateTo = function(viewId) {
        if (viewId === 'loginModal' || viewId === 'signupModal') {
            document.getElementById(viewId).classList.remove('hidden');
            return;
        }

        if (viewId === 'dashboard' && !window.isUserAuthenticated) {
            renderCustomToastNotification("Access Denied: Please log in to use the dashboard.", "error");
            document.getElementById('loginModal').classList.remove('hidden');
            return;
        }

        const viewMapping = {
            'landing': 'restricted-auth-view',
            'dashboard': 'dashboard-core-view',
            'features': 'page-features',
            'help': 'page-help'
        };

        const targetSectionId = viewMapping[viewId];
        if (!targetSectionId) return;

        // Manage single-page application view transitions.
        document.querySelectorAll('.page-view, #dashboard-core-view').forEach(view => {
            view.classList.add('hidden');
            view.classList.remove('active');
        });

        const targetElement = document.getElementById(targetSectionId);
        targetElement.classList.remove('hidden');
        targetElement.classList.add('active');

        // Synchronize active navigation link indicators.
        document.querySelectorAll('.nav-item').forEach(link => link.classList.remove('active'));
        document.getElementById(`link-${viewId}`)?.classList.add('active');
        document.getElementById(`mobile-link-${viewId}`)?.classList.add('active');
        
        if (window.innerWidth < 1024) toggleMobileSidebar(true);
        triggerAudioToneSynthesis('interact');
    };

    window.toggleMobileSidebar = function(forceClose = false) {
        const sidebar = document.getElementById('mobilePopupSidebar');
        const backdrop = document.getElementById('sidebarBackdrop');
        if (!sidebar || !backdrop) return;

        if (forceClose) {
            sidebar.classList.remove('active');
            backdrop.classList.remove('active');
        } else {
            sidebar.classList.toggle('active');
            backdrop.classList.toggle('active');
        }
    };

    window.closeModal = function(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) modal.classList.add('hidden');
    };

    window.switchModal = function(showId, hideId) {
        closeModal(hideId);
        const targetModal = document.getElementById(showId);
        if (targetModal) targetModal.classList.remove('hidden');
    };

    window.handleModalOutSideClick = function(event, modalId) {
        if (event.target.id === modalId) closeModal(modalId);
    };

    window.toggleProfileDropdown = function() {
        document.getElementById('profileDropdown')?.classList.toggle('show');
    };

    window.toggleFAQ = function(element) {
        if (!element) return;
        const panel = element.nextElementSibling;
        const icon = element.querySelector('.faq-icon i');
        const isExpanded = element.getAttribute('aria-expanded') === 'true';
        
        element.setAttribute('aria-expanded', !isExpanded);
        
        if (panel) {
            panel.style.maxHeight = !isExpanded ? `${panel.scrollHeight}px` : null;
        }
        if (icon) {
            icon.className = !isExpanded ? "fa-solid fa-chevron-up" : "fa-solid fa-chevron-down";
        }
    };

    // Real-time FAQ search filter using low-latency input monitoring.
    if (DOMNodes.helpSearchInput) {
        DOMNodes.helpSearchInput.addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase().trim();
            
            DOMNodes.faqItems.forEach(item => {
                const questionText = item.querySelector('.faq-question')?.textContent.toLowerCase() || '';
                const answerText = item.querySelector('.faq-panel')?.textContent.toLowerCase() || '';
                
                if (questionText.includes(query) || answerText.includes(query)) {
                    item.style.display = '';
                } else {
                    item.style.display = 'none';
                }
            });
        });
    }

    // Section: User Authentication Workflows

    window.executeLoginFlow = async function() {
        const email = document.getElementById('loginEmail').value;
        const password = document.getElementById('loginPassword').value;
        const errorBlock = document.getElementById('loginErrorMsg');

        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });
            const result = await response.json();
            if (result.success) {
                window.location.reload();
            } else {
                errorBlock.textContent = result.error || "Authentication failed.";
                errorBlock.classList.remove('hidden');
                triggerAudioToneSynthesis('error');
            }
        } catch (e) {
            renderCustomToastNotification("Network connection failure", "error");
        }
    };

    window.executeSignupFlow = async function() {
        const fullname = document.getElementById('signupName').value;
        const email = document.getElementById('signupEmail').value;
        const password = document.getElementById('signupPassword').value;
        const errorBlock = document.getElementById('signupErrorMsg');

        try {
            const response = await fetch('/api/auth/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ fullname, email, password })
            });
            const result = await response.json();
            if (result.success) {
                window.location.reload();
            } else {
                errorBlock.textContent = result.error || "Registration rejected.";
                errorBlock.classList.remove('hidden');
                triggerAudioToneSynthesis('error');
            }
        } catch (e) {
            renderCustomToastNotification("Registration pipeline dropped", "error");
        }
    };

    window.handleLogout = async function() {
        try {
            await fetch('/api/auth/logout');
        } finally {
            window.location.reload();
        }
    };

    window.showToast = function(msg, type) {
        renderCustomToastNotification(msg, type === 'info' ? 'success' : type);
    };

    // Section: Auditory Feedback and Telemetry Monitoring

    function triggerAudioToneSynthesis(type) {
        try {
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            if (!AudioContextClass) return;
            
            if (!primaryAudioContext) {
                primaryAudioContext = new AudioContextClass();
            }
            
            if (primaryAudioContext.state === 'suspended') {
                primaryAudioContext.resume();
            }
            
            const ctx = primaryAudioContext;
            const osc = ctx.createOscillator();
            const gainNode = ctx.createGain();
            
            osc.connect(gainNode);
            gainNode.connect(ctx.destination);
            const curTime = ctx.currentTime;
            
            if (type === 'success') {
                osc.type = 'sine';
                osc.frequency.setValueAtTime(523.25, curTime); // Pitch: C5
                osc.frequency.setValueAtTime(783.99, curTime + 0.08); // Pitch: G5
                gainNode.gain.setValueAtTime(0.06, curTime);
                gainNode.gain.exponentialRampToValueAtTime(0.00001, curTime + 0.3);
                osc.start(curTime);
                osc.stop(curTime + 0.3);
            } else if (type === 'error') {
                osc.type = 'sawtooth';
                osc.frequency.setValueAtTime(130.81, curTime); // Pitch: C3
                osc.frequency.linearRampToValueAtTime(85.00, curTime + 0.25);
                gainNode.gain.setValueAtTime(0.1, curTime);
                gainNode.gain.exponentialRampToValueAtTime(0.00001, curTime + 0.25);
                osc.start(curTime);
                osc.stop(curTime + 0.25);
            } else if (type === 'interact') {
                osc.type = 'triangle';
                osc.frequency.setValueAtTime(349.23, curTime); // Pitch: F4
                gainNode.gain.setValueAtTime(0.04, curTime);
                gainNode.gain.exponentialRampToValueAtTime(0.00001, curTime + 0.06);
                osc.start(curTime);
                osc.stop(curTime + 0.06);
            }
        } catch (audioException) {
            console.warn("Audio context handshake suspended: Hardware channel occupied.", audioException);
        }
    }

    function renderCustomToastNotification(message, statusType = 'success') {
        if (!DOMNodes.toastContainer) return;
        const notificationCard = document.createElement('div');
        notificationCard.className = `toast-message-card ${statusType}`;
        notificationCard.textContent = message; // Mitigate XSS risks by enforcing text-only output.
        
        DOMNodes.toastContainer.appendChild(notificationCard);
        
        setTimeout(() => {
            notificationCard.style.opacity = '0';
            setTimeout(() => notificationCard.remove(), 300);
        }, 4000);
    }

    async function syncDatastoreHistoryLedger() {
        if (!DOMNodes.historyStreamTarget || !DOMNodes.refreshHistoryBtn) return;
        try {
            DOMNodes.refreshHistoryBtn.classList.add('loading-pulse');
            DOMNodes.historyStreamTarget.style.opacity = '0.5';
            
            const response = await fetch('/api/history');
            const data = await response.json();
            
            if (!data.success) throw new Error(data.error || "Failed to load history arrays");
            
            DOMNodes.historyStreamTarget.innerHTML = '';
            
            if (!data.history || data.history.length === 0) {
                const emptyMsg = document.createElement('div');
                emptyMsg.className = "text-muted text-sm text-center padding-top-md";
                emptyMsg.textContent = "Your history is currently empty.";
                DOMNodes.historyStreamTarget.appendChild(emptyMsg);
                return;
            }
            
            data.history.forEach(record => {
                const row = document.createElement('div');
                row.className = "ledger-row-item";
                
                const header = document.createElement('div');
                header.className = "ledger-row-meta-header";
                
                const nameSpan = document.createElement('span');
                nameSpan.className = "ledger-filename font-mono text-xs";
                nameSpan.textContent = record.filename;
                
                const timeSpan = document.createElement('span');
                timeSpan.className = "ledger-timestamp font-mono";
                timeSpan.textContent = record.timestamp?.split(' ')[1] || record.timestamp || '';
                
                header.appendChild(nameSpan);
                header.appendChild(timeSpan);
                
                const captionDiv = document.createElement('div');
                captionDiv.className = "ledger-caption-text";
                captionDiv.textContent = `[Conf: ${Math.round((record.confidence || 0) * 100)}%] ${record.caption}`;
                
                row.appendChild(header);
                row.appendChild(captionDiv);
                
                DOMNodes.historyStreamTarget.appendChild(row);
            });
        } catch (err) {
            console.error("Ledger structural sync dropped:", err);
            DOMNodes.historyStreamTarget.innerHTML = `<div class="text-pink text-sm text-center">Failed to load history.</div>`;
        } finally {
            DOMNodes.refreshHistoryBtn.classList.remove('loading-pulse');
            DOMNodes.historyStreamTarget.style.opacity = '1';
        }
    }

    // Automated health audit loop to monitor datastore and auth context.
    async function runTelemetryAuditLoop() {
        const statusIndicator = document.getElementById('db-status-indicator');

        try {
            const response = await fetch('/api/telemetry/health');
            const telemetryMatrix = await response.json();
            
            const navAuth = document.getElementById('navAuthSection');
            const profileMenu = document.getElementById('userProfileMenu');
            const profileAvatar = document.getElementById('profileAvatarName');

            // Synchronize local session state with server-side auth response.
            window.isUserAuthenticated = !!(telemetryMatrix.auth_context && telemetryMatrix.auth_context.is_authenticated);

            // Application routing based on current authentication context.
            if (window.isUserAuthenticated) {
                navAuth.classList.add('hidden');
                profileMenu.classList.remove('hidden');
                profileAvatar.textContent = telemetryMatrix.auth_context.fullname.charAt(0).toUpperCase();
                // Automatic redirection to dashboard for authenticated users.
                if (DOMNodes.authView.classList.contains('active')) navigateTo('dashboard');
            } else {
                navAuth.classList.remove('hidden');
                profileMenu.classList.add('hidden');
                // Session expiry logic: redirect to landing page if unauthorized.
                if (DOMNodes.dashboardView.classList.contains('active')) {
                    navigateTo('landing');
                }
            }

            // Update Datastore Status
            if (telemetryMatrix.datastore_status === 'ONLINE') {
                statusIndicator.textContent = "DATABASE CONNECTED";
                statusIndicator.className = "mode-tag badge-gold";
            } else {
                statusIndicator.textContent = "DATABASE OFFLINE (Using local storage)";
                statusIndicator.className = "mode-tag badge-error alertPulse";
            }

        } catch (networkError) {
            console.error("[X] Telemetry pipeline polling interrupted:", networkError);
        } finally {
            setTimeout(runTelemetryAuditLoop, 30000); // Recursive polling interval for telemetry synchronization (30s).
        }
    }

    // Section: File Ingestion and Drag-and-Drop Pipeline

    if (DOMNodes.dropZone) {
        ['dragenter', 'dragover'].forEach(eventName => {
            DOMNodes.dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                DOMNodes.dropZone.classList.add('drag-over');
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            DOMNodes.dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                DOMNodes.dropZone.classList.remove('drag-over');
            }, false);
        });

        DOMNodes.dropZone.addEventListener('drop', (e) => {
            const transferData = e.dataTransfer;
            if (transferData && transferData.files.length > 0) {
                evaluateAndStageFileStream(transferData.files[0]);
            }
        });

        DOMNodes.dropZone.addEventListener('click', () => {
            DOMNodes.fileInput?.click();
        });
    }

    if (DOMNodes.fileInput) {
        DOMNodes.fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                evaluateAndStageFileStream(e.target.files[0]);
            }
        });
    }

    function evaluateAndStageFileStream(file) {
        const validExtensions = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp'];
        
        if (!validExtensions.includes(file.type)) {
            triggerAudioToneSynthesis('error');
            renderCustomToastNotification("Unsupported file type. Please use PNG, JPG, or WebP.", "error");
            return;
        }

        // Ingestion validation: verify file size does not exceed 16MB limit.
        if (file.size > 16 * 1024 * 1024) {
            triggerAudioToneSynthesis('error');
            renderCustomToastNotification("File is too large. Maximum size is 16MB.", "error");
            return;
        }

        uploadedFileStream = file;
        triggerAudioToneSynthesis('interact');

        const reader = new FileReader();
        reader.onload = (event) => {
            if (!DOMNodes.previewFrame) return;
            DOMNodes.previewFrame.innerHTML = '';
            DOMNodes.previewFrame.classList.remove('empty');
            
            const imageNode = document.createElement('img');
            imageNode.src = event.target.result;
            imageNode.alt = "Analytical processing pipeline resource element";
            DOMNodes.previewFrame.appendChild(imageNode);
        };
        reader.readAsDataURL(file);

        if (DOMNodes.inferenceBtn) {
            DOMNodes.inferenceBtn.classList.remove('disabled');
            DOMNodes.inferenceBtn.removeAttribute('disabled');
        }
        renderCustomToastNotification("Image ready for analysis.", "success");
    }

    // Section: Multimodal Inference Execution and UI Updates

    if (DOMNodes.inferenceBtn) {
        DOMNodes.inferenceBtn.addEventListener('click', async () => {
            if (!uploadedFileStream) return;

            triggerAudioToneSynthesis('interact');
            
            DOMNodes.inferenceBtn.classList.add('disabled');
            DOMNodes.inferenceBtn.classList.add('loading-pulse');
            DOMNodes.inferenceBtn.setAttribute('disabled', 'true');
            DOMNodes.captionOutput.innerHTML = '<span class="text-muted italic">Analyzing image... Generating caption...</span>';
            DOMNodes.confidenceScore.textContent = "-- %";
            
            const payloadMatrix = new FormData();
            payloadMatrix.append('image', uploadedFileStream);

            try {
                const response = await fetch('/api/generate-caption', {
                    method: 'POST',
                    body: payloadMatrix
                });

                if (!response.ok) {
                    const structuralErrorPayload = await response.json().catch(() => ({}));
                    throw new Error(structuralErrorPayload.error || `Server HTTP Fault Code: ${response.status}`);
                }

                const analyticalResult = await response.json();

                if (analyticalResult.success) {
                    triggerAudioToneSynthesis('success');
                    
                    DOMNodes.captionOutput.textContent = analyticalResult.caption;
                    DOMNodes.backboneModelMeta.textContent = analyticalResult.backbone || "Modular Vision-Decoder";
                    DOMNodes.confidenceScore.textContent = `${Math.round((analyticalResult.confidence || 0) * 100)} %`;
                    
                    renderCustomToastNotification("Caption generated successfully!", "success");
                    await syncDatastoreHistoryLedger();
                } else {
                    throw new Error(analyticalResult.error || "Multimodal matrix alignment pipeline failure");
                }

            } catch (runtimeFault) {
                triggerAudioToneSynthesis('error');
                DOMNodes.captionOutput.textContent = `Pipeline Drop: ${runtimeFault.message}`;
                DOMNodes.confidenceScore.textContent = "0 %";
                renderCustomToastNotification(runtimeFault.message, "error");
            } finally {
                DOMNodes.inferenceBtn.classList.remove('disabled');
                DOMNodes.inferenceBtn.classList.remove('loading-pulse');
                DOMNodes.inferenceBtn.removeAttribute('disabled');
            }
        });
    }

    if (DOMNodes.copyCaptionBtn) {
        DOMNodes.copyCaptionBtn.addEventListener('click', () => {
            const text = DOMNodes.captionOutput?.textContent.trim() || '';
            const isPlaceholder = text.includes('Initialize high-resolution');
            const isLoading = text.includes('Downsampling spatial coordinates');
            const isError = text.includes('Pipeline Drop');

            if (text && !isPlaceholder && !isLoading && !isError) {
                navigator.clipboard.writeText(text).then(() => {
                    triggerAudioToneSynthesis('interact');
                    renderCustomToastNotification("Caption copied to clipboard", "success");
                });
            } else if (isError || isLoading) {
                renderCustomToastNotification("Invalid state: Cannot copy structural error records.", "error");
            }
        });
    }

    // Section: Component Event Listener Binding

    DOMNodes.refreshHistoryBtn?.addEventListener('click', (e) => {
        e.preventDefault();
        triggerAudioToneSynthesis('interact');
        syncDatastoreHistoryLedger();
    });

    // Initial synchronization of inference history.
    syncDatastoreHistoryLedger();
    runTelemetryAuditLoop(); // Start real-time system telemetry monitoring.
});