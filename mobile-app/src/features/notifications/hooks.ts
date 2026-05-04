import { Platform } from 'react-native';
import * as Application from 'expo-application';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/src/api/client';

export const notificationKeys = {
  prefs: ['notifications', 'preferences'] as const,
};

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

export function useNotificationPreferences() {
  return useQuery({
    queryKey: notificationKeys.prefs,
    queryFn: () => api.getNotificationPreferences(),
    staleTime: 30_000,
  });
}

export function useUpdateNotificationPreferences() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) => api.updateNotificationPreferences({ enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: notificationKeys.prefs }),
  });
}

export async function registerNativePushToken() {
  if (Platform.OS !== 'ios') {
    throw new Error('Push registration is currently supported on iOS only.');
  }

  if (!Device.isDevice) {
    throw new Error('Use a physical iPhone to register for notifications.');
  }

  const permissions = await Notifications.getPermissionsAsync();
  let finalStatus = permissions.status;
  if (finalStatus !== 'granted') {
    const next = await Notifications.requestPermissionsAsync();
    finalStatus = next.status;
  }

  if (finalStatus !== 'granted') {
    throw new Error('Notification permission was not granted.');
  }

  const tokenResponse = await Notifications.getDevicePushTokenAsync();
  return api.registerNotificationDevice({
    token: `${tokenResponse.data}`,
    platform: 'ios',
    environment: __DEV__ ? 'sandbox' : 'production',
    bundle_id: Application.applicationId ?? undefined,
    device_id: Device.osInternalBuildId ?? Device.modelId ?? undefined,
    enabled: true,
  });
}

export function useRegisterDevice() {
  return useMutation({
    mutationFn: registerNativePushToken,
  });
}
