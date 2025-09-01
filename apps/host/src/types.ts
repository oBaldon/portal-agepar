export type NavigationLink = {
  label: string;
  path: string;
  icon?: string; // nome do ícone (ex.: Home)
};

export type BlockRoute =
  | { path: string; kind: "iframe" }
  | { path: string; kind: "react" };

export type BlockUI =
  | { type: "iframe"; url: string }
  | { type: "react"; component?: string };

export type Block = {
  name: string;
  displayName: string;
  version: string;
  ui: BlockUI;
  navigation: NavigationLink[];
  routes: BlockRoute[];
};

export type Catalog = {
  generatedAt: string;
  host: { version: string; minBlockEngine: string };
  blocks: Block[];
};

export type User = {
  cpf: string;
  nome: string;
  email: string;
  roles: string[];
  unidades: string[];
  auth_mode?: string;
};
