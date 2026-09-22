import { createElement, type ReactNode } from "react";
import { vi } from "vitest";
type Props = { children?: ReactNode; [key: string]: unknown };
const native = (name: string) => (props: Props) =>
  createElement(
    name,
    props,
    props.children,
    props.actions as ReactNode,
    props.metadata as ReactNode,
    props.detail as ReactNode,
    props.searchBarAccessory as ReactNode,
  );
const Metadata = Object.assign(native("metadata"), {
  Label: native("label"),
  Separator: native("separator"),
  Link: native("link"),
  TagList: Object.assign(native("tag-list"), { Item: native("tag") }),
});
export const Detail = Object.assign(native("detail"), { Metadata });
export const List = Object.assign(native("list"), {
  Item: Object.assign(native("list-item"), {
    Detail: Object.assign(native("item-detail"), { Metadata }),
  }),
  Section: native("list-section"),
  EmptyView: native("empty"),
  Dropdown: Object.assign(native("dropdown"), {
    Item: native("option"),
    Section: native("option-section"),
  }),
});
export const Form = Object.assign(native("form"), {
  TextField: native("text-field"),
  TextArea: native("text-area"),
  PasswordField: native("password-field"),
  Description: native("description"),
  Checkbox: native("checkbox"),
  Separator: native("separator"),
  Dropdown: Object.assign(native("form-dropdown"), { Item: native("option") }),
});
export const ActionPanel = Object.assign(native("action-panel"), {
  Section: native("action-section"),
  Submenu: native("action-submenu"),
});
export const Action = Object.assign(native("action"), {
  Push: native("push"),
  SubmitForm: native("submit"),
  CopyToClipboard: native("copy"),
  OpenInBrowser: native("open-browser"),
  Style: { Destructive: "destructive" },
});
export const Icon = new Proxy({}, { get: (_, name) => String(name) });
export const Color = new Proxy({}, { get: (_, name) => String(name) });
export const Keyboard = {
  Shortcut: {
    Common: {
      Refresh: { modifiers: ["cmd"], key: "r" },
      Open: { modifiers: ["cmd"], key: "o" },
      New: { modifiers: ["cmd"], key: "n" },
      Save: { modifiers: ["cmd"], key: "s" },
    },
  },
};
export const Toast = {
  Style: { Success: "success", Failure: "failure", Animated: "animated" },
};
export const Alert = { ActionStyle: { Destructive: "destructive" } };
export const showToast = vi.fn(async (options: Record<string, unknown>) => ({
  ...options,
}));
export const confirmAlert = vi.fn(async () => true);
export const navigation = { push: vi.fn(), pop: vi.fn() };
export const useNavigation = () => navigation;
export const getPreferenceValues = vi.fn(() => ({}));
export const openExtensionPreferences = vi.fn();
export const open = vi.fn();
export const launchCommand = vi.fn();
export const LaunchType = { UserInitiated: "user" };
export const Clipboard = { copy: vi.fn() };
export const MenuBarExtra = Object.assign(native("menu"), {
  Item: native("menu-item"),
  Section: native("menu-section"),
  Submenu: native("menu-submenu"),
});
export const storage = new Map<string, unknown>();
export const credentials = new Map<string, { accessToken: string }>();
export const LocalStorage = {
  getItem: vi.fn(async (key: string) => storage.get(key)),
  setItem: vi.fn(async (key: string, value: unknown) => {
    storage.set(key, value);
  }),
  removeItem: vi.fn(async (key: string) => {
    storage.delete(key);
  }),
  allItems: vi.fn(async () => Object.fromEntries(storage)),
};
export const OAuth = {
  RedirectMethod: { App: "app" },
  PKCEClient: class {
    id: string;
    constructor(options: { providerId: string }) {
      this.id = options.providerId;
    }
    async getTokens() {
      return credentials.get(this.id);
    }
    async setTokens(value: { accessToken: string }) {
      credentials.set(this.id, value);
    }
    async removeTokens() {
      credentials.delete(this.id);
    }
  },
};
