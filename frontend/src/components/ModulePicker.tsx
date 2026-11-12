import type { Module } from "../api";

export function ModulePicker({
  modules,
  selected,
  onChange,
  disabled = false,
}: {
  modules: Module[];
  selected: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
}) {
  const toggle = (key: string) =>
    onChange(selected.includes(key) ? selected.filter((k) => k !== key) : [...selected, key]);
  return (
    <ul className="modules">
      {modules.map((module) => (
        <li key={module.key}>
          <label className={`module ${selected.includes(module.key) ? "on" : ""}`}>
            <input
              type="checkbox"
              disabled={disabled}
              checked={selected.includes(module.key)}
              onChange={() => toggle(module.key)}
            />
            <span>
              <span className="module-title">
                <strong>{module.name}</strong>
                {!module.available && <span className="tag">À venir</span>}
              </span>
              <span className="muted module-text">{module.description}</span>
            </span>
          </label>
        </li>
      ))}
    </ul>
  );
}
