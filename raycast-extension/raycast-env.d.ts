/// <reference types="@raycast/api">

/* 🚧 🚧 🚧
 * This file is auto-generated from the extension's manifest.
 * Do not modify manually. Instead, update the `package.json` file.
 * 🚧 🚧 🚧 */

/* eslint-disable @typescript-eslint/ban-types */

type ExtensionPreferences = {
  /** Output Editor - Application used when opening downloaded ssync job output files. */
  "outputEditor": "default" | "vscode" | "cursor" | "ghostty-nvim" | "custom",
  /** Custom Output Editor - Application used when Output Editor is set to Custom Application. */
  "outputEditorApplication"?: import("@raycast/api").Application
}

/** Preferences accessible in all the extension's commands */
declare type Preferences = ExtensionPreferences

declare namespace Preferences {
  /** Preferences accessible in the `jobs` command */
  export type Jobs = ExtensionPreferences & {}
  /** Preferences accessible in the `menu-bar` command */
  export type MenuBar = ExtensionPreferences & {}
}

declare namespace Arguments {
  /** Arguments passed to the `jobs` command */
  export type Jobs = {}
  /** Arguments passed to the `menu-bar` command */
  export type MenuBar = {}
}
