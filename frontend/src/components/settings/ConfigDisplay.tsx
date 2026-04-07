import { useState, useEffect, useMemo } from "react";
import { Card, CardTitle, CardContent } from "../ui/Card";
import {
  useConfig,
  useUpdateConfig,
  useResetConfig,
  useModels,
} from "../../hooks/useConfig";
import { Spinner } from "../ui/Spinner";
import type { ConfigSetting } from "../../api/config";
import {
  RotateCcw,
  Save,
  Eye,
  EyeOff,
  CheckCircle,
  XCircle,
  ChevronDown,
  Search,
  Sliders,
  ToggleRight as ToggleRightIcon,
  Hash,
  Type,
  KeyRound,
  FileText,
} from "lucide-react";
import { cn } from "../../lib/utils";

function groupSettings(
  settings: ConfigSetting[],
): Record<string, ConfigSetting[]> {
  const groups: Record<string, ConfigSetting[]> = {};
  for (const s of settings) {
    if (!groups[s.group]) groups[s.group] = [];
    groups[s.group].push(s);
  }
  return groups;
}

function SensitiveInput({
  setting,
  value,
  onChange,
}: {
  setting: ConfigSetting;
  value: string;
  onChange: (val: string) => void;
}) {
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState(false);
  const [localVal, setLocalVal] = useState("");

  const handleStartEdit = () => {
    setEditing(true);
    setLocalVal("");
  };

  const handleConfirm = () => {
    if (localVal) {
      onChange(localVal);
    }
    setEditing(false);
  };

  const handleCancel = () => {
    setEditing(false);
    setLocalVal("");
  };

  if (editing) {
    return (
      <div className="flex items-center gap-1.5">
        <input
          type={show ? "text" : "password"}
          value={localVal}
          onChange={(e) => setLocalVal(e.target.value)}
          placeholder="Enter new value..."
          autoFocus
          onKeyDown={(e) => {
            if (e.key === "Enter") handleConfirm();
            if (e.key === "Escape") handleCancel();
          }}
          className="w-56 rounded-md border border-blue-400 bg-white px-3 py-1.5 text-sm text-gray-900 dark:border-blue-500 dark:bg-gray-700 dark:text-gray-100"
        />
        <button
          type="button"
          onClick={() => setShow(!show)}
          className="rounded p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
        >
          {show ? (
            <EyeOff className="h-3.5 w-3.5" />
          ) : (
            <Eye className="h-3.5 w-3.5" />
          )}
        </button>
        <button
          onClick={handleConfirm}
          className="rounded p-1 text-green-500 hover:text-green-600"
          title="Confirm"
        >
          <CheckCircle className="h-4 w-4" />
        </button>
        <button
          onClick={handleCancel}
          className="rounded p-1 text-red-400 hover:text-red-500"
          title="Cancel"
        >
          <XCircle className="h-4 w-4" />
        </button>
      </div>
    );
  }

  const hasValue = setting.has_value;

  return (
    <div className="flex items-center gap-2">
      {hasValue ? (
        <code className="max-w-[10rem] truncate rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-700 dark:text-gray-400">
          {value}
        </code>
      ) : (
        <span className="text-sm italic text-gray-400 dark:text-gray-500">
          not set
        </span>
      )}
      <button
        onClick={handleStartEdit}
        className="shrink-0 rounded bg-gray-100 px-2 py-1 text-xs font-medium text-gray-600 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
      >
        {hasValue ? "Change" : "Set"}
      </button>
    </div>
  );
}

function ModelSelect({
  value,
  onChange,
  provider = "openai",
}: {
  value: string;
  onChange: (val: string) => void;
  provider?: "openai" | "gemini" | "all";
}) {
  const { data, isLoading } = useModels(provider);
  const models = data?.models ?? [];

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-56 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
    >
      {isLoading && <option value={value}>{value} (loading...)</option>}
      {!isLoading && models.length === 0 && (
        <option value={value}>{value}</option>
      )}
      {models.map((m) => (
        <option key={m} value={m}>
          {m}
        </option>
      ))}
      {!isLoading && models.length > 0 && !models.includes(value) && (
        <option value={value}>{value} (current)</option>
      )}
    </select>
  );
}

function SettingInput({
  setting,
  value,
  onChange,
}: {
  setting: ConfigSetting;
  value: string | number | boolean;
  onChange: (val: string | number | boolean) => void;
}) {
  if (setting.sensitive) {
    return (
      <SensitiveInput
        setting={setting}
        value={value as string}
        onChange={onChange}
      />
    );
  }

  if (setting.key === "AGENT_MODEL") {
    return <ModelSelect value={value as string} onChange={onChange} />;
  }

  if (setting.model_picker) {
    return (
      <ModelSelect
        value={value as string}
        onChange={onChange}
        provider={setting.model_picker as "openai" | "gemini" | "all"}
      />
    );
  }

  if (setting.choices && setting.choices.length > 0) {
    return (
      <select
        value={value as string}
        onChange={(e) => onChange(e.target.value)}
        className="w-56 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
      >
        {setting.choices.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
        {!setting.choices.includes(value as string) && (
          <option value={value as string}>{value as string} (current)</option>
        )}
      </select>
    );
  }

  if (setting.type === "bool") {
    return (
      <button
        type="button"
        role="switch"
        aria-checked={!!value}
        onClick={() => onChange(!value)}
        className={cn(
          "relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors",
          value ? "bg-blue-600" : "bg-gray-300 dark:bg-gray-600",
        )}
      >
        <span
          className={cn(
            "pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow ring-0 transition-transform",
            value ? "translate-x-5" : "translate-x-0",
          )}
        />
      </button>
    );
  }

  if (setting.key.endsWith("_CUSTOM_INSTRUCTIONS")) {
    return (
      <textarea
        value={value as string}
        onChange={(e) => onChange(e.target.value)}
        rows={4}
        className="w-72 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
      />
    );
  }

  if (setting.type === "int" || setting.type === "float") {
    return (
      <input
        type="number"
        value={value as number}
        step={setting.type === "float" ? "0.1" : "1"}
        min={setting.min_value ?? undefined}
        max={setting.max_value ?? undefined}
        onChange={(e) => {
          const v =
            setting.type === "float"
              ? parseFloat(e.target.value)
              : parseInt(e.target.value, 10);
          if (!isNaN(v)) onChange(v);
        }}
        className="w-32 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
      />
    );
  }

  return (
    <input
      type="text"
      value={value as string}
      onChange={(e) => onChange(e.target.value)}
      className="w-48 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
    />
  );
}

// ---------------------------------------------------------------------------
// Sub-group settings by visual type
// ---------------------------------------------------------------------------

type SettingCategory = "toggle" | "number" | "credential" | "text" | "textarea";

function categorize(s: ConfigSetting): SettingCategory {
  if (s.key.endsWith("_CUSTOM_INSTRUCTIONS")) return "textarea";
  if (s.sensitive) return "credential";
  if (s.type === "bool") return "toggle";
  if (s.type === "int" || s.type === "float") return "number";
  return "text";
}

const CATEGORY_META: Record<
  SettingCategory,
  { icon: React.ReactNode; label: string }
> = {
  toggle: {
    icon: <ToggleRightIcon className="h-3.5 w-3.5" />,
    label: "Toggles",
  },
  number: { icon: <Hash className="h-3.5 w-3.5" />, label: "Values" },
  credential: {
    icon: <KeyRound className="h-3.5 w-3.5" />,
    label: "Credentials",
  },
  text: { icon: <Type className="h-3.5 w-3.5" />, label: "Text" },
  textarea: {
    icon: <FileText className="h-3.5 w-3.5" />,
    label: "Custom Instructions",
  },
};

const CATEGORY_ORDER: SettingCategory[] = [
  "toggle",
  "number",
  "text",
  "credential",
  "textarea",
];

function subGroupSettings(
  settings: ConfigSetting[],
): { category: SettingCategory; items: ConfigSetting[] }[] {
  const map = new Map<SettingCategory, ConfigSetting[]>();
  for (const s of settings) {
    const cat = categorize(s);
    if (!map.has(cat)) map.set(cat, []);
    map.get(cat)!.push(s);
  }
  return CATEGORY_ORDER.filter((c) => map.has(c)).map((c) => ({
    category: c,
    items: map.get(c)!,
  }));
}

// ---------------------------------------------------------------------------
// Setting row component
// ---------------------------------------------------------------------------

function SettingRow({
  setting,
  localValues,
  dirty,
  onChangeValue,
  onReset,
  isDefault,
  resetPending,
  isToggle,
}: {
  setting: ConfigSetting;
  localValues: Record<string, string | number | boolean>;
  dirty: Set<string>;
  onChangeValue: (key: string, value: string | number | boolean) => void;
  onReset: (key: string) => void;
  isDefault: (setting: ConfigSetting) => boolean;
  resetPending: boolean;
  isToggle?: boolean;
}) {
  const isDirty = dirty.has(setting.key);

  if (isToggle) {
    // Compact toggle row: label + description on left, toggle on right
    return (
      <div
        className={cn(
          "flex items-center justify-between gap-4 rounded-lg px-3 py-2.5 transition-colors",
          isDirty
            ? "bg-amber-50 ring-1 ring-amber-200 dark:bg-amber-900/10 dark:ring-amber-800"
            : "hover:bg-gray-50 dark:hover:bg-gray-700/20",
        )}
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
              {setting.label}
            </span>
            {isDirty && (
              <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                modified
              </span>
            )}
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {setting.description}
          </p>
        </div>
        <SettingInput
          setting={setting}
          value={localValues[setting.key] ?? setting.value}
          onChange={(v) => onChangeValue(setting.key, v)}
        />
      </div>
    );
  }

  // Standard row for inputs/text/credentials
  return (
    <div
      className={cn(
        "rounded-lg px-3 py-2.5 transition-colors",
        isDirty
          ? "bg-amber-50 ring-1 ring-amber-200 dark:bg-amber-900/10 dark:ring-amber-800"
          : "hover:bg-gray-50 dark:hover:bg-gray-700/20",
      )}
    >
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
              {setting.label}
            </span>
            {setting.sensitive && setting.has_value && !isDirty && (
              <span className="rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700 dark:bg-green-900/30 dark:text-green-400">
                set
              </span>
            )}
            {setting.sensitive && !setting.has_value && !isDirty && (
              <span className="rounded bg-red-100 px-1.5 py-0.5 text-xs text-red-700 dark:bg-red-900/30 dark:text-red-400">
                not set
              </span>
            )}
            {isDirty && (
              <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                modified
              </span>
            )}
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {setting.description}
            {setting.min_value != null && setting.max_value != null && (
              <span className="ml-1">
                ({setting.min_value} – {setting.max_value})
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <SettingInput
            setting={setting}
            value={localValues[setting.key] ?? setting.value}
            onChange={(v) => onChangeValue(setting.key, v)}
          />
          {!setting.sensitive && !isDefault(setting) && (
            <button
              onClick={() => onReset(setting.key)}
              disabled={resetPending}
              title={`Reset to default (${setting.default})`}
              className="rounded p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Accordion group — now with sub-grouping by type
// ---------------------------------------------------------------------------

function AccordionGroup({
  group,
  settings,
  localValues,
  dirty,
  onChangeValue,
  onReset,
  isDefault,
  resetPending,
  defaultOpen,
  searchQuery,
}: {
  group: string;
  settings: ConfigSetting[];
  localValues: Record<string, string | number | boolean>;
  dirty: Set<string>;
  onChangeValue: (key: string, value: string | number | boolean) => void;
  onReset: (key: string) => void;
  isDefault: (setting: ConfigSetting) => boolean;
  resetPending: boolean;
  defaultOpen: boolean;
  searchQuery: string;
}) {
  const [open, setOpen] = useState(defaultOpen);

  const dirtyCount = settings.filter((s) => dirty.has(s.key)).length;
  const subGroups = useMemo(() => subGroupSettings(settings), [settings]);

  // Auto-open when search matches
  useEffect(() => {
    if (searchQuery && settings.length > 0) setOpen(true);
  }, [searchQuery, settings.length]);

  return (
    <div className="border-b border-gray-100 last:border-b-0 dark:border-gray-700/50">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-5 py-3 text-left transition-colors hover:bg-gray-50 dark:hover:bg-gray-700/20"
      >
        <div className="flex items-center gap-2">
          <h4 className="text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
            {group}
          </h4>
          <span className="text-xs text-gray-400">({settings.length})</span>
          {dirtyCount > 0 && (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
              {dirtyCount} modified
            </span>
          )}
        </div>
        <ChevronDown
          className={cn(
            "h-4 w-4 text-gray-400 transition-transform",
            open && "rotate-180",
          )}
        />
      </button>

      {open && (
        <div className="px-5 pb-4 space-y-4">
          {subGroups.map(({ category, items }) => {
            const meta = CATEGORY_META[category];
            const showSubHeader = subGroups.length > 1;

            return (
              <div key={category}>
                {showSubHeader && (
                  <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-gray-400 dark:text-gray-500">
                    {meta.icon}
                    <span>{meta.label}</span>
                    <div className="ml-1 flex-1 border-t border-gray-100 dark:border-gray-700/50" />
                  </div>
                )}
                <div className="space-y-1">
                  {items.map((setting) => (
                    <SettingRow
                      key={setting.key}
                      setting={setting}
                      localValues={localValues}
                      dirty={dirty}
                      onChangeValue={onChangeValue}
                      onReset={onReset}
                      isDefault={isDefault}
                      resetPending={resetPending}
                      isToggle={category === "toggle"}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ConfigDisplay() {
  const { data, isLoading, error } = useConfig();
  const updateMutation = useUpdateConfig();
  const resetMutation = useResetConfig();

  const [localValues, setLocalValues] = useState<
    Record<string, string | number | boolean>
  >({});
  const [dirty, setDirty] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    if (data?.settings) {
      const vals: Record<string, string | number | boolean> = {};
      for (const s of data.settings) {
        vals[s.key] = s.value;
      }
      setLocalValues(vals);
      setDirty(new Set());
    }
  }, [data]);

  const filteredGroups = useMemo(() => {
    if (!data?.settings) return {};
    const groups = groupSettings(data.settings);
    if (!searchQuery.trim()) return groups;
    const q = searchQuery.toLowerCase();
    const result: Record<string, ConfigSetting[]> = {};
    for (const [group, settings] of Object.entries(groups)) {
      const matched = settings.filter(
        (s) =>
          s.label.toLowerCase().includes(q) ||
          s.key.toLowerCase().includes(q) ||
          s.description.toLowerCase().includes(q),
      );
      if (matched.length > 0) result[group] = matched;
    }
    return result;
  }, [data, searchQuery]);

  if (isLoading) {
    return (
      <Card>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <Spinner />
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error || !data) {
    return (
      <Card>
        <CardContent>
          <p className="text-sm text-red-500">Failed to load configuration.</p>
        </CardContent>
      </Card>
    );
  }

  const handleChange = (key: string, value: string | number | boolean) => {
    setLocalValues((prev) => ({ ...prev, [key]: value }));
    setDirty((prev) => new Set(prev).add(key));
  };

  const handleSave = () => {
    const changes: Record<string, string | number | boolean> = {};
    for (const key of dirty) {
      changes[key] = localValues[key];
    }
    if (Object.keys(changes).length === 0) return;
    updateMutation.mutate(changes, {
      onSuccess: () => setDirty(new Set()),
    });
  };

  const handleReset = (key: string) => {
    resetMutation.mutate(key);
  };

  const isDefault = (setting: ConfigSetting) => {
    if (setting.sensitive) return !setting.has_value && !dirty.has(setting.key);
    return (
      localValues[setting.key] === setting.default && !dirty.has(setting.key)
    );
  };

  const groupEntries = Object.entries(filteredGroups);

  return (
    <Card padding={false}>
      {/* Header */}
      <div className="flex items-center justify-between gap-3 px-5 pt-5 pb-3">
        <div className="flex items-center gap-2">
          <Sliders className="h-5 w-5 text-indigo-500" />
          <CardTitle>Configuration</CardTitle>
        </div>
        {/* Search */}
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search settings..."
            className="w-52 rounded-lg border border-gray-200 bg-gray-50 py-1.5 pl-8 pr-3 text-xs text-gray-700 placeholder-gray-400 focus:border-indigo-400 focus:bg-white focus:outline-none dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:placeholder-gray-500 dark:focus:border-indigo-500"
          />
        </div>
      </div>

      {/* Accordion groups */}
      {groupEntries.length === 0 ? (
        <div className="px-5 pb-5 text-center text-sm text-gray-400">
          No settings match "{searchQuery}"
        </div>
      ) : (
        <div>
          {groupEntries.map(([group, settings]) => (
            <AccordionGroup
              key={group}
              group={group}
              settings={settings}
              localValues={localValues}
              dirty={dirty}
              onChangeValue={handleChange}
              onReset={handleReset}
              isDefault={isDefault}
              resetPending={resetMutation.isPending}
              defaultOpen={settings.some((s) => dirty.has(s.key))}
              searchQuery={searchQuery}
            />
          ))}
        </div>
      )}

      {/* Sticky save bar */}
      {dirty.size > 0 && (
        <div className="sticky bottom-0 flex items-center justify-between rounded-b-xl border-t border-gray-200 bg-white/90 px-5 py-3 backdrop-blur dark:border-gray-700 dark:bg-gray-800/90">
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {dirty.size} unsaved {dirty.size === 1 ? "change" : "changes"}
          </span>
          <button
            onClick={handleSave}
            disabled={updateMutation.isPending}
            className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 disabled:opacity-50"
          >
            <Save className="h-4 w-4" />
            {updateMutation.isPending ? "Saving..." : `Save (${dirty.size})`}
          </button>
        </div>
      )}
    </Card>
  );
}
