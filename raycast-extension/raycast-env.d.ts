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
  "outputEditorApplication"?: import("@raycast/api").Application,
  /** Menu Bar Jobs per Section - Maximum number of jobs shown in each menu bar section. */
  "menuBarJobLimit": "5" | "8" | "15" | "20",
  /** Menu Bar Attention - Show failed, timed out, and preempted jobs in the menu bar. */
  "menuBarAttention": boolean
}

/** Preferences accessible in all the extension's commands */
declare type Preferences = ExtensionPreferences

declare namespace Preferences {
  /** Preferences accessible in the `jobs` command */
  export type Jobs = ExtensionPreferences & {}
  /** Preferences accessible in the `menu-bar` command */
  export type MenuBar = ExtensionPreferences & {}
  /** Preferences accessible in the `hosts` command */
  export type Hosts = ExtensionPreferences & {}
  /** Preferences accessible in the `connections` command */
  export type Connections = ExtensionPreferences & {}
  /** Preferences accessible in the `watchers` command */
  export type Watchers = ExtensionPreferences & {}
  /** Preferences accessible in the `launch` command */
  export type Launch = ExtensionPreferences & {}
}

declare namespace Arguments {
  /** Arguments passed to the `jobs` command */
  export type Jobs = {}
  /** Arguments passed to the `menu-bar` command */
  export type MenuBar = {}
  /** Arguments passed to the `hosts` command */
  export type Hosts = {}
  /** Arguments passed to the `connections` command */
  export type Connections = {}
  /** Arguments passed to the `watchers` command */
  export type Watchers = {}
  /** Arguments passed to the `launch` command */
  export type Launch = {}
}
