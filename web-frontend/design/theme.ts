import tokens from '../src/lib/design/relay-tokens.json';

// Use the same Relay tokens as the production frontend, mirrored from iOS.
const aliases = {
  canvas: 'Canvas', rail: 'Canvas', surface: 'Surface', raised: 'SurfaceSecondary',
  text: 'Ink', secondary: 'InkSecondary', muted: 'InkSecondary', border: 'Separator',
  accent: 'Accent', 'accent-ink': 'OnAccent', 'accent-soft': 'AccentSoft',
  blue: 'Running', 'blue-soft': 'AccentSoft', green: 'Success', 'green-soft': 'SuccessSoft',
  amber: 'Warning', 'amber-soft': 'WarningSoft', red: 'Danger', 'red-soft': 'DangerSoft',
  console: 'CodeCanvas',
} satisfies Record<string, keyof typeof tokens.colors>;

export function installRelayTheme() {
  const style = document.getElementById('relay-tokens') ?? document.createElement('style');
  style.id = 'relay-tokens';
  const themes = ['light', 'dark'] as const;
  style.textContent = themes.map(theme => {
    const colors = Object.entries(aliases).map(([alias, token]) => `--${alias}:${tokens.colors[token][theme]};`).join('');
    return `:root[data-theme="${theme}"]{color-scheme:${theme};${colors}}`;
  }).join('\n') + `\n:root{
    ${themes.flatMap(theme => Object.entries(tokens.colors).map(([name, color]) => `--relay-${theme}-${name}:${color[theme]};`)).join('')}
    --radius-inset:${tokens.radius.inset}px;
    --radius-control:${tokens.radius.control}px;
    --radius-card:${tokens.radius.card}px;
    --motion-press:${tokens.motion.pressMilliseconds}ms;
    --motion-state:${tokens.motion.stateMilliseconds}ms;
    --motion-disclosure:${tokens.motion.disclosureMilliseconds}ms;
  }`;
  if (!style.isConnected) document.head.append(style);
}
