import { beforeEach } from "vitest";
import { storage, credentials } from "./raycast";
(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;
beforeEach(() => {
  storage.clear();
  credentials.clear();
});
