import { createElement } from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { afterEach, expect, it, vi } from "vitest";
import { useResource } from "./useResource";

let tree: ReactTestRenderer | undefined;
afterEach(async () => {
  if (tree) await act(async () => tree!.unmount());
  tree = undefined;
});
function Probe({
  scope,
  load,
}: {
  scope: string;
  load: (signal: AbortSignal) => Promise<string>;
}) {
  const resource = useResource(scope, load);
  return createElement("div", resource);
}
it("ignores a late response after changing scope and aborts its request", async () => {
  let finishFirst!: (value: string) => void;
  let firstSignal!: AbortSignal;
  const first = vi.fn((signal: AbortSignal) => {
    firstSignal = signal;
    return new Promise<string>((resolve) => {
      finishFirst = resolve;
    });
  });
  await act(async () => {
    tree = create(<Probe scope="first" load={first} />);
  });
  await act(async () =>
    tree!.update(<Probe scope="second" load={async () => "second response"} />),
  );
  expect(firstSignal.aborted).toBe(true);
  await act(async () => finishFirst("outdated response"));
  expect(tree!.root.findByType("div").props.data).toBe("second response");
});
it("retains the last useful content on refresh failure", async () => {
  const loader = vi
    .fn<() => Promise<string>>()
    .mockResolvedValueOnce("received output")
    .mockRejectedValueOnce(new Error("Offline"));
  await act(async () => {
    tree = create(<Probe scope="job" load={loader} />);
  });
  await act(async () => {
    expect(await tree!.root.findByType("div").props.refresh()).toBe(false);
  });
  const state = tree!.root.findByType("div").props;
  expect(state.data).toBe("received output");
  expect(state.error).toBe("Offline");
  expect(state.isLoading).toBe(false);
});
