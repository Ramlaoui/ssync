import { act, create, type ReactTestRenderer } from "react-test-renderer";
import { afterEach, expect, it, vi } from "vitest";
import { SsyncClient } from "../api/client";
import { getConnection } from "../api/storage";
import { connection } from "../test/fixtures";
import { ConnectionForm } from "./ConnectionForm";
let tree: ReactTestRenderer;
afterEach(async () => {
  if (tree) await act(async () => tree.unmount());
  vi.restoreAllMocks();
});
it("clears credentials and certificate trust across an incomplete URL edit", async () => {
  await act(async () => {
    tree = create(
      <ConnectionForm
        initial={{ ...connection, allowSelfSigned: true }}
        onConfigured={() => {}}
      />,
    );
  });
  await act(async () => {
    tree.root.findByProps({ id: "apiUrl" }).props.onChange("");
  });
  await act(async () => {
    tree.root
      .findByProps({ id: "apiUrl" })
      .props.onChange("https://different.test");
  });
  expect(tree.root.findByProps({ id: "apiKey" }).props.value).toBe("");
  expect(tree.root.findByProps({ id: "allowSelfSigned" }).props.value).toBe(
    false,
  );
});
it("validates fields before connecting and prevents duplicate saves", async () => {
  let finish!: () => void;
  const test = vi
    .spyOn(SsyncClient.prototype, "testConnection")
    .mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = () => resolve();
        }),
    );
  const configured = vi.fn();
  await act(async () => {
    tree = create(<ConnectionForm onConfigured={configured} />);
  });
  await act(async () => {
    tree.root.findByProps({ id: "jobLimit" }).props.onChange("0");
  });
  await act(async () => {
    await tree.root.findByProps({ title: "Connect" }).props.onSubmit();
  });
  expect(test).not.toHaveBeenCalled();
  expect(tree.root.findByProps({ id: "jobLimit" }).props.error).toBeTruthy();
  await act(async () => {
    tree.root.findByProps({ id: "jobLimit" }).props.onChange("25");
  });
  const submit = tree.root.findByProps({ title: "Connect" }).props.onSubmit;
  let pending: Promise<void>;
  await act(async () => {
    pending = submit();
    void submit();
  });
  expect(test).toHaveBeenCalledTimes(1);
  await act(async () => {
    finish();
    await pending;
  });
  expect(configured).toHaveBeenCalledTimes(1);
  expect((await getConnection())?.jobLimit).toBe(25);
});
