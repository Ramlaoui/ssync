import React, { useEffect, useState } from "react";
import { Folder, FolderOpen, Home, RefreshCw } from "lucide-react-native";
import { Pressable, StyleSheet, View } from "react-native";

import type { SsyncApiClient } from "../api/client";
import type { LocalEntry } from "../types/api";
import type { Palette } from "../theme/colors";
import { AppText, Button, Card, EmptyState, IconButton, SectionHeader, Sheet, TextField } from "./ui";

export function FileBrowserSheet({
  palette,
  api,
  visible,
  initialPath,
  onSelect,
  onClose
}: {
  palette: Palette;
  api: SsyncApiClient;
  visible: boolean;
  initialPath: string;
  onSelect: (path: string) => void;
  onClose: () => void;
}) {
  const [path, setPath] = useState(initialPath || "/home");
  const [entries, setEntries] = useState<LocalEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load(nextPath = path) {
    setLoading(true);
    setError(null);
    try {
      const response = await api.listLocalPath(nextPath, true);
      setPath(response.path);
      setEntries(response.entries);
    } catch (loadError) {
      setError((loadError as Error).message || "Failed to list path");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (visible) void load(initialPath || path || "/home");
  }, [visible]);

  function parentPath(): string {
    const trimmed = path.replace(/\/+$/, "");
    const parent = trimmed.split("/").slice(0, -1).join("/");
    return parent || "/";
  }

  return (
    <Sheet palette={palette} visible={visible} title="Source Directory" onClose={onClose}>
      <Card palette={palette}>
        <TextField palette={palette} label="Path" value={path} onChangeText={setPath} />
        <View style={styles.actions}>
          <Button palette={palette} title="Open" icon={FolderOpen} onPress={() => load(path)} loading={loading} />
          <Button palette={palette} title="Parent" icon={Home} variant="secondary" onPress={() => load(parentPath())} />
          <IconButton palette={palette} icon={RefreshCw} label="Refresh" onPress={() => load(path)} />
        </View>
        <Button
          palette={palette}
          title="Use this directory"
          icon={Folder}
          variant="secondary"
          onPress={() => {
            onSelect(path);
            onClose();
          }}
        />
      </Card>

      {error ? <Card palette={palette}><SectionHeader palette={palette} title="Error" subtitle={error} /></Card> : null}

      <Card palette={palette}>
        <SectionHeader palette={palette} title="Folders" subtitle={`${entries.length} directories`} />
        {entries.length === 0 ? (
          <EmptyState palette={palette} title={loading ? "Loading" : "No folders"} icon={Folder} />
        ) : (
          entries.map((entry) => (
            <Pressable
              key={entry.path}
              onPress={() => load(entry.path)}
              style={({ pressed }) => [
                styles.entry,
                { borderColor: palette.border, opacity: pressed ? 0.75 : 1 }
              ]}
            >
              <Folder size={18} color={palette.muted} />
              <View style={{ flex: 1 }}>
                <AppText palette={palette} weight="800">{entry.name}</AppText>
                <AppText palette={palette} muted size={12} numberOfLines={1}>{entry.path}</AppText>
              </View>
            </Pressable>
          ))
        )}
      </Card>
    </Sheet>
  );
}

const styles = StyleSheet.create({
  actions: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8
  },
  entry: {
    minHeight: 54,
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingVertical: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 10
  }
});
