import AsyncStorage from '@react-native-async-storage/async-storage';
import { createJSONStorage, persist } from 'zustand/middleware';
import { create } from 'zustand';

type LaunchDraftField = 'host' | 'sourceDir' | 'scriptContent' | 'jobName' | 'partition' | 'cpus' | 'mem' | 'time';

type LaunchDraftState = {
  host: string;
  sourceDir: string;
  scriptContent: string;
  jobName: string;
  partition: string;
  cpus: string;
  mem: string;
  time: string;
  setField: (field: LaunchDraftField, value: string) => void;
  reset: () => void;
};

const initialState = {
  host: '',
  sourceDir: '',
  scriptContent: '#!/bin/bash\n\npython train.py\n',
  jobName: '',
  partition: '',
  cpus: '',
  mem: '',
  time: '',
};

export const useLaunchDraftStore = create<LaunchDraftState>()(
  persist(
    (set) => ({
      ...initialState,
      setField: (field, value) => set({ [field]: value } as Pick<LaunchDraftState, typeof field>),
      reset: () => set(initialState),
    }),
    {
      name: 'ssync.launch-draft',
      storage: createJSONStorage(() => AsyncStorage),
    },
  ),
);
