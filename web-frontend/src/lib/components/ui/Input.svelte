<script lang="ts">
  import { createBubbler } from 'svelte/legacy';

  const bubble = createBubbler();
  import { cn } from "../../cn";
  import type { HTMLInputAttributes } from "svelte/elements";

  type $$Props = HTMLInputAttributes & {
    class?: string;
  };


  interface Props extends Omit<HTMLInputAttributes, 'value' | 'class'> {
    class?: string;
    value?: string | number | null | undefined;
  }

  type $$Events = {
    input: Event;
    change: Event;
    focus: FocusEvent;
    blur: FocusEvent;
    keydown: KeyboardEvent;
    keyup: KeyboardEvent;
    keypress: KeyboardEvent;
  };

  let { class: className = "", value = $bindable(undefined), ...rest }: Props = $props();
</script>

<input
  {...rest}
  bind:value
  class={cn(
    "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
    className
  )}
  oninput={bubble('input')}
  onchange={bubble('change')}
  onfocus={bubble('focus')}
  onblur={bubble('blur')}
  onkeydown={bubble('keydown')}
  onkeyup={bubble('keyup')}
/>
