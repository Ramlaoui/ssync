<script lang="ts">
  import { onMount, type Snippet } from 'svelte';
  import Icon from './Icon.svelte';
  let {title,onclose,children,wide=false,busy=false}:{title:string;onclose:()=>void;children:Snippet;wide?:boolean;busy?:boolean}=$props();
  let dialog: HTMLDialogElement;
  onMount(()=>{dialog.showModal();return ()=>dialog.close();});
</script>
<dialog bind:this={dialog} class:wide aria-label={title} aria-busy={busy} onclose={onclose} oncancel={(e)=>{if(busy)e.preventDefault();}} onclick={(e)=>{if(!busy&&e.target===dialog){const box=dialog.getBoundingClientRect();if(e.clientX<box.left||e.clientX>box.right||e.clientY<box.top||e.clientY>box.bottom)dialog.close();}}} onkeydown={()=>{}}>
  <div class="modal-header"><h2>{title}</h2><button class="icon-button" aria-label="Close dialog" title="Close" disabled={busy} onclick={()=>dialog.close()}><Icon name="X"/></button></div>
  {@render children()}
</dialog>
