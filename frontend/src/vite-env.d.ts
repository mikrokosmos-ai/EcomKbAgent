/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_IMPORT_API?: string;
  readonly VITE_QUERY_API?: string;
  readonly VITE_DEV_IMPORT_TARGET?: string;
  readonly VITE_DEV_QUERY_TARGET?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
