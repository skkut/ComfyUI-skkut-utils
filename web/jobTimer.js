import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

/**
 * ComfyUI Detailed Job Status – Execution Timer
 *
 * A floating, draggable widget that shows how long the current job
 * has been *executing* (not queued) in MM:SS format.
 *
 * Completion detection:
 *   - `execution_success` is the definitive "workflow done" event.
 *   - `executing{node:...}` fires many times throughout a run (including for
 *     cached nodes) and is NOT a reliable completion signal — we ignore it.
 */
app.registerExtension({
    name: "DetailedJobStatus.ExecutionTimer",

    setup() {
        // ── State ────────────────────────────────────────────────────────────
        let startTime = null;
        let tickInterval = null;
        let currentPromptId = null;

        // ── Build Widget ─────────────────────────────────────────────────────
        const widget = document.createElement("div");
        widget.id = "djs-timer-widget";

        const savedPos = JSON.parse(localStorage.getItem("djs-timer-pos") || "null");

        Object.assign(widget.style, {
            position: "fixed",
            zIndex: "9999",
            right: savedPos ? "auto" : "16px",
            bottom: savedPos ? "auto" : "64px",
            left: savedPos ? savedPos.left + "px" : "auto",
            top: savedPos ? savedPos.top + "px" : "auto",
            display: "none",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            minWidth: "110px",
            padding: "10px 16px",
            borderRadius: "10px",
            background: "rgba(20, 20, 28, 0.88)",
            backdropFilter: "blur(8px)",
            border: "1px solid rgba(255,255,255,0.12)",
            boxShadow: "0 4px 24px rgba(0,0,0,0.5)",
            color: "#e0e0e0",
            fontFamily: "'Segoe UI', system-ui, monospace",
            cursor: "grab",
            userSelect: "none",
            opacity: "1",
        });

        const label = document.createElement("div");
        Object.assign(label.style, {
            fontSize: "10px",
            fontWeight: "600",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: "rgba(255,255,255,0.45)",
            marginBottom: "4px",
        });
        label.textContent = "Running";

        const timerDisplay = document.createElement("div");
        Object.assign(timerDisplay.style, {
            fontSize: "28px",
            fontWeight: "700",
            fontFamily: "monospace",
            letterSpacing: "0.04em",
            lineHeight: "1",
            color: "#ffffff",
        });
        timerDisplay.textContent = "0:00";

        widget.appendChild(label);
        widget.appendChild(timerDisplay);
        document.body.appendChild(widget);

        // ── Drag to Move ─────────────────────────────────────────────────────
        let dragging = false, dragOffX = 0, dragOffY = 0;

        widget.addEventListener("mousedown", (e) => {
            dragging = true;
            dragOffX = e.clientX - widget.getBoundingClientRect().left;
            dragOffY = e.clientY - widget.getBoundingClientRect().top;
            widget.style.cursor = "grabbing";
            widget.style.right = "auto";
            widget.style.bottom = "auto";
            e.preventDefault();
            e.stopPropagation();
        });
        widget.addEventListener("click", (e) => e.stopPropagation());
        widget.addEventListener("pointerdown", (e) => e.stopPropagation());

        document.addEventListener("mousemove", (e) => {
            if (!dragging) return;
            widget.style.left = (e.clientX - dragOffX) + "px";
            widget.style.top  = (e.clientY - dragOffY) + "px";
        });
        document.addEventListener("mouseup", () => {
            if (!dragging) return;
            dragging = false;
            widget.style.cursor = "grab";
            const rect = widget.getBoundingClientRect();
            localStorage.setItem("djs-timer-pos", JSON.stringify({ left: rect.left, top: rect.top }));
        });

        // ── Helpers ──────────────────────────────────────────────────────────
        function formatElapsed(ms) {
            const totalSec = Math.floor(ms / 1000);
            const m = Math.floor(totalSec / 60);
            const s = totalSec % 60;
            return `${m}:${s.toString().padStart(2, "0")}`;
        }

        function showWidget(labelText, timerText, accentColor) {
            label.textContent = labelText;
            timerDisplay.textContent = timerText;
            timerDisplay.style.color = accentColor || "#ffffff";
            widget.style.display = "flex";
            widget.style.opacity = "1";
        }

        function startTicking() {
            if (tickInterval) clearInterval(tickInterval);
            tickInterval = setInterval(() => {
                if (startTime === null) return;
                timerDisplay.textContent = formatElapsed(Date.now() - startTime);
            }, 1000);
        }

        function stopTicking() {
            if (tickInterval) { clearInterval(tickInterval); tickInterval = null; }
        }

        function resetWidget() {
            stopTicking();
            startTime = null;
            currentPromptId = null;
            widget.style.display = "none";
            widget.style.opacity = "1";
            timerDisplay.style.color = "#ffffff";
            label.textContent = "Running";
        }

        // Returns true if the event belongs to the currently tracked job.
        function isCurrentJob(event) {
            const evtId = event?.detail?.prompt_id;
            if (!evtId || !currentPromptId) return true;
            return evtId === currentPromptId;
        }

        // ── WebSocket Event Listeners ─────────────────────────────────────────

        // Fired when a prompt actually begins executing (not when queued).
        api.addEventListener("execution_start", (event) => {
            resetWidget();
            currentPromptId = event.detail?.prompt_id ?? null;
            startTime = Date.now();
            showWidget("Running", "0:00", "#ffffff");
            startTicking();
        });

        // Definitive "entire workflow finished" signal — fires exactly once at
        // true completion. Confirmed via event logging on ComfyUI Desktop.
        api.addEventListener("execution_success", (event) => {
            if (startTime === null) return;
            if (!isCurrentJob(event)) return;
            stopTicking();
            const elapsed = formatElapsed(Date.now() - startTime);
            startTime = null;
            currentPromptId = null;
            showWidget("Completed", elapsed, "#6fcf97");
        });

        // Fired when an error stops execution.
        api.addEventListener("execution_error", (event) => {
            if (startTime === null) return;
            if (!isCurrentJob(event)) return;
            stopTicking();
            const elapsed = formatElapsed(Date.now() - startTime);
            startTime = null;
            currentPromptId = null;
            showWidget("Error", elapsed, "#eb5757");
        });

        // Fired when the user interrupts a running job.
        api.addEventListener("execution_interrupted", (event) => {
            if (startTime === null) return;
            if (!isCurrentJob(event)) return;
            stopTicking();
            const elapsed = formatElapsed(Date.now() - startTime);
            startTime = null;
            currentPromptId = null;
            showWidget("Stopped", elapsed, "#f2994a");
        });
    },
});
