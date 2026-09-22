<script lang="ts">
  import { Activity, ArrowDown, ArrowLeft, ArrowRight, ArrowUpRight, Bell, Check, CheckCheck, ChevronDown, ChevronRight, Circle, Clock3, Command, Copy, Cpu, Database, Download, Ellipsis, Eye, FileCode2, Filter, Folder, GitBranch, Layers, ListFilter, LoaderCircle, Maximize2, Minimize2, Menu, Moon, Pause, Play, Plus, Radio, RefreshCw, Rocket, Search, Server, Settings2, SlidersHorizontal, Sparkles, Square, Sun, Terminal, TriangleAlert, Workflow, X, Zap } from 'lucide-svelte';
  let {name, size=18, strokeWidth=1.7, class:className=''}:{name:string;size?:number;strokeWidth?:number;class?:string}=$props();
  const icons: Record<string, typeof Activity> = {Activity,ArrowDown,ArrowLeft,ArrowRight,ArrowUpRight,Bell,Check,CheckCheck,ChevronDown,ChevronRight,Circle,Clock3,Command,Copy,Cpu,Database,Download,Ellipsis,Eye,FileCode2,Filter,Folder,GitBranch,Layers,ListFilter,LoaderCircle,Maximize2,Minimize2,Menu,Moon,Pause,Play,Plus,Radio,RefreshCw,Rocket,Search,Server,Settings2,SlidersHorizontal,Sparkles,Square,Sun,Terminal,TriangleAlert,Workflow,X,Zap};
  const Glyph=$derived(icons[name] || Circle);
</script>
<Glyph {size} {strokeWidth} class={className} aria-hidden="true" />
