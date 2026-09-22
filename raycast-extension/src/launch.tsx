import { ConnectionGate } from "./components/ConnectionGate";
import { LaunchView } from "./components/LaunchView";
export default function Command() {
  return (
    <ConnectionGate>
      {(connection) => <LaunchView connection={connection} />}
    </ConnectionGate>
  );
}
