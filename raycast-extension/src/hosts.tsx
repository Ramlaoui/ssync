import { ConnectionGate } from "./components/ConnectionGate";
import { HostsView } from "./components/HostsView";
export default function Command() {
  return (
    <ConnectionGate>
      {(connection, reload) => (
        <HostsView connection={connection} onConnectionChanged={reload} />
      )}
    </ConnectionGate>
  );
}
