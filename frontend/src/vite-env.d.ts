/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_DEV_SERVER_PORT?: string;
  readonly VITE_AUTH_RETURN_TO?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
