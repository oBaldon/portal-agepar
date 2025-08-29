export type Catalog = {
  generatedAt: string;
  host: { version: string; minBlockEngine: string };
  blocks: Block[];
};
export type Block = {
  name: string;
  displayName: string;
  version: string;
  ui: { type: "iframe"; url: string };
  navigation: { label: string; path: string; icon?: string }[];
  routes: { path: string; kind: "iframe" }[];
};
export type User = {
  cpf: string;
  name: string;
  email: string;
  roles: string[];
  unidades?: string[];
};
