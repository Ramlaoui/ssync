<script lang="ts">
  import Icon from './Icon.svelte';
  let {state}:{state:string}=$props();
  const color=$derived(['Running','Active'].includes(state)?'blue':['Pending','Timed out'].includes(state)?'amber':state==='Failed'?'red':state==='Completed'?'green':'neutral');
  const icon=$derived(['Running','Active'].includes(state)?'Activity':state==='Pending'?'Clock3':state==='Completed'?'Check':['Failed','Timed out'].includes(state)?'TriangleAlert':'Pause');
</script>
<span class="status {color}"><Icon name={icon} size={13}/>{state}</span>
