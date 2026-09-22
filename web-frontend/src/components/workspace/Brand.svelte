<script lang="ts">
  let { size = 34 }: {
    size?: number;
  } = $props();
</script>

<!-- Relay mark, from ios/assets/brand/relay-mark-cobalt.svg. -->

<svg width={size} height={size} viewBox="0 0 100 100" fill="none" aria-hidden="true">
  <g stroke="currentColor" stroke-width="10" stroke-linecap="round" stroke-linejoin="round">
    <path d="M76 22H43C30 22 22 30 22 42H55" />
    <path d="M24 78H57C70 78 78 70 78 58H45" />
  </g>
</svg>
