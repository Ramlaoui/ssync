import { ConnectionGate } from "./components/ConnectionGate";
import { WatchersView } from "./components/WatchersView";
export default function Command() {
  return (
    <ConnectionGate>
      {(connection) => <WatchersView connection={connection} />}
    </ConnectionGate>
  );
}
