/**
 * Browser notification service for job status updates
 */

interface NotificationOptions {
  title: string;
  body: string;
  icon?: string;
  tag?: string;
  requireInteraction?: boolean;
  silent?: boolean;
}

type NotificationMessageOptions = {
  type: string;
  message: string;
  duration?: number;
};

class NotificationService {
  private enabled: boolean = false;
  private soundEnabled: boolean = false;
  private audioContext: AudioContext | null = null;
  private notificationSound: HTMLAudioElement | null = null;

  constructor() {
    this.loadPreferences();
    this.initAudio();

    // Listen for preference changes
    window.addEventListener('notificationSettingsChanged', (event: CustomEvent) => {
      const { showNotifications, soundAlerts } = event.detail;
      this.enabled = showNotifications;
      this.soundEnabled = soundAlerts;
    });
  }

  private loadPreferences() {
    const savedPrefs = localStorage.getItem('ssync_preferences');
    if (savedPrefs) {
      try {
        const prefs = JSON.parse(savedPrefs);
        this.enabled = prefs.showNotifications || false;
        this.soundEnabled = prefs.soundAlerts || false;
      } catch (e) {
        console.error('Failed to load notification preferences:', e);
      }
    }
  }

  private initAudio() {
    // Create a simple notification sound using Web Audio API
    try {
      this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
    } catch (e) {
      console.warn('Web Audio API not supported');
    }
  }

  private async playNotificationSound() {
    if (!this.soundEnabled || !this.audioContext) return;

    try {
      // Create a simple beep sound
      const oscillator = this.audioContext.createOscillator();
      const gainNode = this.audioContext.createGain();

      oscillator.connect(gainNode);
      gainNode.connect(this.audioContext.destination);

      oscillator.frequency.value = 800; // Frequency in Hz
      gainNode.gain.value = 0.1; // Volume

      oscillator.start();
      oscillator.stop(this.audioContext.currentTime + 0.2); // Play for 200ms
    } catch (e) {
      console.error('Failed to play notification sound:', e);
    }
  }

  public async requestPermission(): Promise<NotificationPermission> {
    if (!('Notification' in window)) {
      console.warn('Browser does not support notifications');
      return 'denied';
    }

    return await Notification.requestPermission();
  }

  public async notify(
    options: NotificationOptions | NotificationMessageOptions
  ): Promise<void> {
    const normalizedOptions = this.normalizeOptions(options);
    if (!this.enabled) return;

    if (!('Notification' in window)) {
      console.warn('Browser does not support notifications');
      return;
    }

    if (Notification.permission !== 'granted') {
      const permission = await this.requestPermission();
      if (permission !== 'granted') return;
    }

    try {
      const notification = new Notification(normalizedOptions.title, {
        body: normalizedOptions.body,
        icon: normalizedOptions.icon || '/favicon.ico',
        tag: normalizedOptions.tag,
        requireInteraction: normalizedOptions.requireInteraction || false,
        silent: normalizedOptions.silent || !this.soundEnabled,
      });

      // Play sound if enabled and not silent
      if (this.soundEnabled && !normalizedOptions.silent) {
        await this.playNotificationSound();
      }

      // Auto-close after 10 seconds unless requireInteraction is true
      if (!normalizedOptions.requireInteraction) {
        setTimeout(() => notification.close(), 10000);
      }

      // Handle click
      notification.onclick = () => {
        window.focus();
        notification.close();
      };
    } catch (e) {
      console.error('Failed to show notification:', e);
    }
  }

  private normalizeOptions(
    options: NotificationOptions | NotificationMessageOptions
  ): NotificationOptions {
    if ('title' in options) {
      return options;
    }

    const title =
      options.type === 'error'
        ? 'Error'
        : options.type === 'warning'
          ? 'Warning'
          : options.type === 'success'
            ? 'Success'
            : 'Notification';

    return {
      title,
      body: options.message,
    };
  }

  public notifyNewJob(jobId: string, hostname: string, state: string, jobName: string) {
    const stateDescriptions: Record<string, string> = {
      'PD': 'pending',
      'R': 'running',
      'CD': 'completed',
      'F': 'failed',
      'CA': 'cancelled',
      'TO': 'timed out',
    };

    const stateDesc = stateDescriptions[state] || state;

    let title = `New job ${jobId}`;
    let body = `${jobName} submitted to ${hostname}`;

    // Customize based on initial state
    if (state === 'R') {
      title = `New job ${jobId} running`;
      body = `${jobName} started immediately on ${hostname}`;
    } else if (state === 'PD') {
      title = `New job ${jobId} submitted`;
      body = `${jobName} is pending on ${hostname}`;
    }

    this.notify({
      title,
      body,
      tag: `new-job-${jobId}`,
      requireInteraction: false,
    });
  }

  public notifyJobStateChange(jobId: string, hostname: string, oldState: string, newState: string) {
    const stateDescriptions: Record<string, string> = {
      'PD': 'pending',
      'R': 'running',
      'CD': 'completed',
      'F': 'failed',
      'CA': 'cancelled',
      'TO': 'timed out',
    };

    const oldStateDesc = stateDescriptions[oldState] || oldState;
    const newStateDesc = stateDescriptions[newState] || newState;

    let title = `Job ${jobId} ${newStateDesc}`;
    let body = `Job on ${hostname} changed from ${oldStateDesc} to ${newStateDesc}`;

    // Customize based on state
    if (newState === 'R') {
      title = `Job ${jobId} started`;
      body = `Your job on ${hostname} is now running`;
    } else if (newState === 'CD') {
      title = `Job ${jobId} completed`;
      body = `Your job on ${hostname} has finished successfully`;
    } else if (newState === 'F') {
      title = `Job ${jobId} failed`;
      body = `Your job on ${hostname} has failed`;
    }

    this.notify({
      title,
      body,
      tag: `job-${jobId}`,
      requireInteraction: newState === 'F', // Keep failure notifications visible
    });
  }

  public notifyBatchComplete(count: number, hostname?: string) {
    const location = hostname ? `on ${hostname}` : '';
    this.notify({
      title: `${count} jobs completed`,
      body: `${count} jobs have finished ${location}`,
      tag: 'batch-complete',
    });
  }
}

// Create singleton instance
export const notificationService = new NotificationService();
