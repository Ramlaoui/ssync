import React, { useMemo, useState } from "react";
import { Bell, BellOff, RotateCcw } from "lucide-react-native";

import { AppText, Card, Button, SectionHeader, SegmentedControl, Sheet } from "./ui";
import type { Palette } from "../theme/colors";
import type { JobInfo } from "../types/api";
import type { JobNotificationConfig } from "../types/settings";
import { compactJobTitle, jobKey } from "../utils/format";
import { defaultJobNotificationConfig } from "../services/notifications";

export function JobNotificationSheet({
  palette,
  visible,
  job,
  config,
  onSave,
  onReset,
  onClose
}: {
  palette: Palette;
  visible: boolean;
  job: JobInfo | null;
  config?: JobNotificationConfig;
  onSave: (key: string, config: JobNotificationConfig) => void;
  onReset: (key: string) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<JobNotificationConfig>(() => config || defaultJobNotificationConfig());

  React.useEffect(() => {
    if (visible) {
      setDraft(config || defaultJobNotificationConfig());
    }
  }, [config, visible]);

  const key = useMemo(() => (job ? jobKey(job.job_id, job.hostname) : ""), [job]);

  if (!job) return null;

  return (
    <Sheet palette={palette} visible={visible} title="Job Notifications" onClose={onClose}>
      <Card palette={palette}>
        <SectionHeader
          palette={palette}
          title={compactJobTitle(job)}
          subtitle={`${job.hostname} - configure this job without changing global defaults`}
        />
        <SegmentedControl
          palette={palette}
          value={draft.mode}
          options={[
            { value: "inherit", label: "Inherit" },
            { value: "muted", label: "Muted" }
          ]}
          onChange={(mode) => setDraft({ ...draft, mode })}
        />
        <AppText palette={palette} muted size={12}>
          Backend notifications support per-job muting. Status filters are configured globally in Settings.
        </AppText>
      </Card>

      {draft.mode === "muted" ? (
        <Card palette={palette}>
          <SectionHeader palette={palette} title="Muted" subtitle="This job will not raise native alerts on this device." />
          <Button palette={palette} title="Save muted rule" icon={BellOff} onPress={() => onSave(key, draft)} />
        </Card>
      ) : null}

      <Card palette={palette}>
        <Button palette={palette} title={draft.mode === "muted" ? "Save muted rule" : "Use global defaults"} icon={Bell} onPress={() => onSave(key, draft)} disabled={!key} />
        <Button palette={palette} title="Reset to global defaults" icon={RotateCcw} variant="secondary" onPress={() => onReset(key)} disabled={!config} />
      </Card>
    </Sheet>
  );
}
