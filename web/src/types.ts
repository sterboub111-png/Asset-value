export type Rec = Record<string, any>;

export interface Lookups {
  categories: Rec[];
  locations: Rec[];
  costcenters: Rec[];
  glaccounts: Rec[];
  methods: Rec[];
  periods: Rec[];
  settings: Record<string, string>;
  statuses: string[];
  maint_types: string[];
  maint_priorities: string[];
  maint_statuses: string[];
  user: string;
}

export type ColType = "text" | "money" | "date" | "int" | "pct" | "status" | "bool";

export interface Col {
  key: string;
  label: string;
  type?: ColType;
  width?: number;
  link?: (row: Rec) => string | null;
  render?: (row: Rec) => Node | string;
  hidden?: boolean;
}

export interface ReportResult {
  id: string;
  title?: string;
  subtitle?: string;
  company: string;
  currency: string;
  generated: string;
  params: Record<string, string>;
  columns: { key: string; label: string; type: ColType }[];
  rows: Rec[];
  group_by?: string;
  totals?: string[];
  subtotal_only?: string[];
}
