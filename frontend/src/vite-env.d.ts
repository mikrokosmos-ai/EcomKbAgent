/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_IMPORT_API?: string;
  readonly VITE_QUERY_API?: string;
  /** 导入侧端口（`--service both` 下 SPA 在 query 端口、导入路由在 import 端口时用于跨端口寻址） */
  readonly VITE_IMPORT_PORT?: string;
  readonly VITE_DEV_IMPORT_TARGET?: string;
  readonly VITE_DEV_QUERY_TARGET?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
