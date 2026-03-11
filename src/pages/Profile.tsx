import { useState } from "react";
import { ChevronRight, Check } from "lucide-react";
import { useStore } from "../store/useStore";
import Modal from "../components/Modal";
import { useToast } from "../components/Toast";

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!value)}
      className={`w-12 h-7 rounded-full relative transition-colors ${
        value ? "bg-accent-green" : "bg-bg-cell"
      }`}
    >
      <span
        className={`absolute top-0.5 w-6 h-6 rounded-full bg-white shadow transition-transform ${
          value ? "translate-x-5.5" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

export default function Profile() {
  const store = useStore();
  const { toast } = useToast();
  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState(store.settings.displayName);
  const [riskModal, setRiskModal] = useState(false);
  const [changelogModal, setChangelogModal] = useState(false);

  const initials = store.settings.displayName
    .split(" ")
    .map((w) => w[0])
    .join("")
    .toUpperCase();

  const riskModes = ["Conservative", "Balanced", "Aggressive"] as const;

  const accentColors = [
    { key: "blue" as const, color: "#0A84FF" },
    { key: "green" as const, color: "#30D158" },
    { key: "purple" as const, color: "#BF5AF2" },
    { key: "orange" as const, color: "#FF9F0A" },
  ];

  return (
    <div className="p-4 md:p-6 max-w-2xl mx-auto">
      {/* Avatar */}
      <div className="flex flex-col items-center mb-8">
        <div className="w-20 h-20 rounded-full flex items-center justify-center text-2xl font-bold mb-3" style={{ background: "var(--accent-color)" }}>
          {initials}
        </div>
        {editingName ? (
          <div className="flex items-center gap-2">
            <input
              autoFocus
              value={nameInput}
              onChange={(e) => setNameInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  store.setDisplayName(nameInput);
                  setEditingName(false);
                }
              }}
              className="h-9 px-3 rounded-lg bg-bg-elevated border border-border-subtle text-sm text-center focus:outline-none"
            />
            <button
              onClick={() => {
                store.setDisplayName(nameInput);
                setEditingName(false);
              }}
              className="w-9 h-9 rounded-lg flex items-center justify-center"
              style={{ background: "var(--accent-color)" }}
            >
              <Check size={16} />
            </button>
          </div>
        ) : (
          <button
            onClick={() => setEditingName(true)}
            className="text-xl font-bold hover:text-text-secondary transition-colors"
          >
            {store.settings.displayName}
          </button>
        )}
        <span className="mt-1 text-xs font-semibold px-2 py-0.5 rounded bg-accent-gold/15 text-accent-gold">
          PRO TRADER
        </span>
      </div>

      {/* Settings groups */}
      <div className="space-y-6">
        {/* Bot Preferences */}
        <Section title="Bot Preferences">
          <Row
            label="Risk Tolerance"
            value={store.botStatus.riskMode}
            onClick={() => setRiskModal(true)}
          />
          <RowToggle
            label="Auto-Trade"
            value={store.botStatus.autoTrade}
            onChange={store.setAutoTrade}
          />
          <div className="px-4 py-3 flex items-center justify-between">
            <span className="text-sm text-text-primary">Max Position Size</span>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={100}
                max={5000}
                step={100}
                value={store.botStatus.maxPositionSize}
                onChange={(e) => store.setMaxPositionSize(parseInt(e.target.value))}
                className="w-32 accent-blue-500"
              />
              <span className="font-mono text-sm text-text-primary w-14 text-right">
                ${store.botStatus.maxPositionSize}
              </span>
            </div>
          </div>
        </Section>

        {/* Notifications */}
        <Section title="Notifications">
          <RowToggle label="Price Alerts" value={store.settings.notifications.priceAlerts} onChange={(v) => store.setNotification("priceAlerts", v)} />
          <RowToggle label="Bot Recommendations" value={store.settings.notifications.botRecs} onChange={(v) => store.setNotification("botRecs", v)} />
          <RowToggle label="Odds Movement" value={store.settings.notifications.oddsMovement} onChange={(v) => store.setNotification("oddsMovement", v)} />
          <RowToggle label="Market Resolving" value={store.settings.notifications.resolving} onChange={(v) => store.setNotification("resolving", v)} />
        </Section>

        {/* Account */}
        <Section title="Account">
          <Row
            label="Balance"
            value={`$${store.portfolio.balance.toLocaleString("en-US", { minimumFractionDigits: 2 })}`}
          />
          <Row label="Deposit" onClick={() => toast("Coming soon", "info")} />
          <Row label="Withdraw" onClick={() => toast("Coming soon", "info")} />
          <div className="px-4 py-3 flex items-center justify-between">
            <span className="text-sm text-text-primary">API Status</span>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-accent-green" />
              <span className="text-sm text-accent-green">Connected</span>
            </div>
          </div>
        </Section>

        {/* Appearance */}
        <Section title="Appearance">
          <Row label="Theme" value="Dark" onClick={() => toast("Coming soon", "info")} />
          <div className="px-4 py-3">
            <p className="text-sm text-text-primary mb-3">Accent Color</p>
            <div className="flex gap-3">
              {accentColors.map((c) => (
                <button
                  key={c.key}
                  onClick={() => store.setAccentColor(c.key)}
                  className="w-9 h-9 rounded-full border-2 flex items-center justify-center transition-transform"
                  style={{
                    backgroundColor: c.color,
                    borderColor: store.settings.accentColor === c.key ? "#FFFFFF" : "transparent",
                    transform: store.settings.accentColor === c.key ? "scale(1.15)" : "scale(1)",
                  }}
                >
                  {store.settings.accentColor === c.key && <Check size={14} className="text-white" />}
                </button>
              ))}
            </div>
          </div>
        </Section>

        {/* About */}
        <Section title="About">
          <Row label="Version" value="1.0.0" />
          <Row label="What's New" onClick={() => setChangelogModal(true)} />
          <Row label="Rate App" onClick={() => toast("Thanks for the feedback!", "success")} />
        </Section>
      </div>

      {/* Risk mode modal */}
      <Modal open={riskModal} onClose={() => setRiskModal(false)}>
        <div>
          <h3 className="text-lg font-bold mb-4">Risk Tolerance</h3>
          <div className="space-y-2">
            {riskModes.map((mode) => (
              <button
                key={mode}
                onClick={() => {
                  store.setRiskMode(mode);
                  setRiskModal(false);
                  toast(`Risk mode set to ${mode}`, "success");
                }}
                className={`w-full px-4 py-3 rounded-xl text-sm font-medium text-left transition-colors ${
                  store.botStatus.riskMode === mode
                    ? "text-white"
                    : "bg-bg-elevated text-text-secondary hover:text-text-primary"
                }`}
                style={store.botStatus.riskMode === mode ? { background: "var(--accent-color)" } : undefined}
              >
                {mode}
              </button>
            ))}
          </div>
        </div>
      </Modal>

      {/* Changelog modal */}
      <Modal open={changelogModal} onClose={() => setChangelogModal(false)}>
        <div>
          <h3 className="text-lg font-bold mb-3">What's New — v1.0.0</h3>
          <ul className="space-y-2 text-sm text-text-secondary">
            <li>• Complete UI redesign with dark theme</li>
            <li>• AI-powered market analysis and recommendations</li>
            <li>• Real-time position tracking with P&L</li>
            <li>• Smart alert system with bot digest</li>
            <li>• Interactive chat interface with Kalshi-Bot</li>
            <li>• Customizable risk tolerance and notifications</li>
          </ul>
          <button
            onClick={() => setChangelogModal(false)}
            className="mt-4 w-full h-11 rounded-xl text-sm font-semibold text-white"
            style={{ background: "var(--accent-color)" }}
          >
            Got It
          </button>
        </div>
      </Modal>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h2 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2 px-1">
        {title}
      </h2>
      <div className="card divide-y divide-border-subtle p-0 overflow-hidden">{children}</div>
    </div>
  );
}

function Row({
  label,
  value,
  onClick,
}: {
  label: string;
  value?: string;
  onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-white/5 transition-colors"
      disabled={!onClick && !value}
    >
      <span className="text-sm text-text-primary">{label}</span>
      <div className="flex items-center gap-1">
        {value && <span className="text-sm text-text-secondary">{value}</span>}
        {onClick && <ChevronRight size={16} className="text-text-tertiary" />}
      </div>
    </button>
  );
}

function RowToggle({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="px-4 py-3 flex items-center justify-between">
      <span className="text-sm text-text-primary">{label}</span>
      <Toggle value={value} onChange={onChange} />
    </div>
  );
}
