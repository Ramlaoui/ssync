export {};

declare global {
  interface WindowEventMap {
    notificationSettingsChanged: CustomEvent<{
      showNotifications: boolean;
      soundAlerts: boolean;
    }>;
    jobsPerPageChanged: CustomEvent<{
      jobsPerPage: number;
    }>;
  }
}
