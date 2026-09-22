import tokens from './relay-tokens.json';
// Relay tokens are mirrored from ios/design/tokens.json so standalone web builds
// and the Python package do not require the iOS project to be present.
const aliases = {
    background: 'Canvas', foreground: 'Ink', card: 'Surface', 'card-foreground': 'Ink',
    popover: 'Surface', 'popover-foreground': 'Ink', input: 'Surface', border: 'Separator',
    muted: 'SurfaceSecondary', 'muted-foreground': 'InkSecondary', secondary: 'SurfaceSecondary',
    'secondary-foreground': 'Ink', primary: 'Accent', 'primary-foreground': 'OnAccent',
    accent: 'Accent', 'accent-foreground': 'OnAccent', 'accent-soft': 'AccentSoft', ring: 'Accent',
    running: 'Running', success: 'Success', 'success-bg': 'SuccessSoft', warning: 'Warning',
    'warning-bg': 'WarningSoft', error: 'Danger', 'error-bg': 'DangerSoft',
    destructive: 'Danger', 'destructive-foreground': 'Surface', info: 'Accent', 'info-bg': 'AccentSoft',
    'code-background': 'CodeCanvas',
} satisfies Record<string, keyof typeof tokens.colors>;
export function installRelayTheme(): void {
    const style = document.getElementById('ssync-relay-tokens') ?? document.createElement('style');
    style.id = 'ssync-relay-tokens';
    style.textContent = (['light', 'dark'] as const).map(appearance => {
        const values = Object.entries(aliases).map(([name, token]) => `--${name}:${tokens.colors[token][appearance]};`);
        const shades = ['Canvas', 'Surface', 'SurfaceSecondary', 'Separator', 'InkSecondary', 'InkSecondary', 'InkSecondary', 'Ink', 'Ink', 'Ink'] as const;
        for (const scale of ['gray', 'slate']) {
            [50, 100, 200, 300, 400, 500, 600, 700, 800, 900].forEach((shade, i) => values.push(`--${scale}-${shade}:${tokens.colors[shades[i]][appearance]};`));
        }
        return `${appearance === 'light' ? ':root' : ':root.dark'}{color-scheme:${appearance};${values.join('')}}`;
    }).join('\n') + `:root{--radius:12px;--radius-card:${tokens.radius.card}px;--motion-fast:${tokens.motion.pressMilliseconds}ms;--motion-state:${tokens.motion.stateMilliseconds}ms;--motion-disclosure:${tokens.motion.disclosureMilliseconds}ms;}`;
    if (!style.isConnected)
        document.head.append(style);
}
