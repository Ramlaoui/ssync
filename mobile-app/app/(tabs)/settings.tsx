import { Platform, StyleSheet, Switch, Text, View } from 'react-native';
import { useState } from 'react';

import { Screen } from '@/src/components/Screen';
import { EmptyState } from '@/src/components/EmptyState';
import { PrimaryButton } from '@/src/components/PrimaryButton';
import { SectionCard } from '@/src/components/SectionCard';
import { TextField } from '@/src/components/TextField';
import {
  useNotificationPreferences,
  useRegisterDevice,
  useUpdateNotificationPreferences,
} from '@/src/features/notifications/hooks';
import { useSessionStore } from '@/src/features/session/session-store';
import { api } from '@/src/api/client';
import { colors } from '@/src/theme/colors';

export default function SettingsScreen() {
  const baseUrl = useSessionStore((state) => state.baseUrl);
  const apiKey = useSessionStore((state) => state.apiKey);
  const saveSession = useSessionStore((state) => state.saveSession);
  const clearSession = useSessionStore((state) => state.clearSession);
  const isSaving = useSessionStore((state) => state.isSaving);
  const [draftBaseUrl, setDraftBaseUrl] = useState(baseUrl);
  const [draftApiKey, setDraftApiKey] = useState(apiKey);
  const [connectionMessage, setConnectionMessage] = useState<string | null>(null);

  const notificationPreferences = useNotificationPreferences();
  const registerDevice = useRegisterDevice();
  const updateNotificationPreferences = useUpdateNotificationPreferences();

  return (
    <Screen
      eyebrow="Session"
      title="Server trust, auth, and alerts"
      subtitle="Use this screen to bind the mobile client to a local or remote ssync server. Notification registration is iOS-only with the current backend."
    >
      <SectionCard title="Server" subtitle="The app stores the base URL in local persistence and the API key in the secure keychain.">
        <TextField
          label="Base URL"
          value={draftBaseUrl}
          onChangeText={setDraftBaseUrl}
          placeholder="https://localhost:8042"
          autoCapitalize="none"
          autoCorrect={false}
          hint="Self-signed local certificates still need to be trusted by the device; this client does not bypass TLS trust."
        />
        <TextField
          label="API key"
          value={draftApiKey}
          onChangeText={setDraftApiKey}
          placeholder="optional"
          autoCapitalize="none"
          autoCorrect={false}
          secureTextEntry
        />
        <PrimaryButton
          label="Save session"
          loading={isSaving}
          onPress={() => saveSession({ baseUrl: draftBaseUrl, apiKey: draftApiKey })}
        />
        <PrimaryButton
          label="Test connection"
          tone="ghost"
          onPress={async () => {
            try {
              await saveSession({ baseUrl: draftBaseUrl, apiKey: draftApiKey });
              const health = await api.healthcheck();
              setConnectionMessage(health.message ?? health.status ?? 'Server responded successfully.');
            } catch (error) {
              setConnectionMessage(`${error}`);
            }
          }}
        />
        <PrimaryButton label="Clear session" tone="danger" onPress={clearSession} />
        {connectionMessage ? <Text style={styles.message}>{connectionMessage}</Text> : null}
      </SectionCard>

      <SectionCard title="Notifications" subtitle="Current backend support is APNs-only. Android builds should keep alerts disabled until the server grows a second transport.">
        {Platform.OS !== 'ios' ? (
          <EmptyState
            title="iOS-only in the current backend"
            body="The server accepts APNs device tokens only. Keep the shared UI honest instead of pretending Android push is wired."
          />
        ) : (
          <>
            <View style={styles.toggleRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.toggleTitle}>Enable job notifications</Text>
                <Text style={styles.toggleBody}>Sync alert preferences to the ssync server.</Text>
              </View>
              <Switch
                value={notificationPreferences.data?.enabled ?? false}
                onValueChange={(value) => updateNotificationPreferences.mutate(value)}
              />
            </View>
            <PrimaryButton
              label="Register this device"
              loading={registerDevice.isPending}
              onPress={() => registerDevice.mutate()}
            />
          </>
        )}
        {registerDevice.error ? <Text style={styles.error}>{`${registerDevice.error}`}</Text> : null}
      </SectionCard>
    </Screen>
  );
}

const styles = StyleSheet.create({
  message: {
    color: colors.textMuted,
  },
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  toggleTitle: {
    color: colors.text,
    fontWeight: '700',
  },
  toggleBody: {
    color: colors.textMuted,
    fontSize: 13,
    lineHeight: 18,
  },
  error: {
    color: colors.danger,
  },
});
