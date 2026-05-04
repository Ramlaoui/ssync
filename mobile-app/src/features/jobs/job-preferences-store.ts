import AsyncStorage from '@react-native-async-storage/async-storage';
import { createJSONStorage, persist } from 'zustand/middleware';
import { create } from 'zustand';

type JobFiltersState = {
  search: string;
  host: string;
  state: string;
  user: string;
  setSearch: (value: string) => void;
  setHost: (value: string) => void;
  setState: (value: string) => void;
  setUser: (value: string) => void;
};

export const useJobFiltersStore = create<JobFiltersState>()(
  persist(
    (set) => ({
      search: '',
      host: '',
      state: '',
      user: '',
      setSearch: (search) => set({ search }),
      setHost: (host) => set({ host }),
      setState: (state) => set({ state }),
      setUser: (user) => set({ user }),
    }),
    {
      name: 'ssync.job-filters',
      storage: createJSONStorage(() => AsyncStorage),
    },
  ),
);
