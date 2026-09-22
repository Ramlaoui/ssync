import Observation
import SwiftUI

@MainActor @Observable final class OutputModel {
  var buffer = OutputBuffer()
  var connected = false
  var loading = true
  var error: String?
  var revision = 0
  var updatedAt: Date?
  var complete = false
  var lines: [String] { buffer.text.components(separatedBy: "\n") }

  func watch(api: APIClient?, id: JobID, source: String, demo: Bool, snapshotURL: URL?) async {
    buffer.replace("")
    revision += 1
    complete = false
    connected = false
    loading = true
    error = nil
    if demo {
      buffer.replace(DemoData.output(source))
      loading = false
      connected = true
      updatedAt = .now
      revision += 1
      return
    }
    if let snapshotURL, let data = try? Data(contentsOf: snapshotURL),
      let saved = try? JSONDecoder().decode(SavedOutput.self, from: data)
    {
      buffer.replace(saved.text, truncated: saved.truncated)
      updatedAt = saved.receivedAt
      loading = false
      revision += 1
    }
    var lastSaved = Date.distantPast
    func saveSnapshot() {
      guard let snapshotURL, let updatedAt, !buffer.text.isEmpty else { return }
      let snapshot = SavedOutput(
        text: buffer.text, truncated: buffer.trimmed, receivedAt: updatedAt)
      if let data = try? JSONEncoder().encode(snapshot) {
        try? data.write(
          to: snapshotURL, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
      }
      lastSaved = .now
    }
    defer { saveSnapshot() }
    guard let api else {
      loading = false
      return
    }
    while !Task.isCancelled {
      do {
        var request = try api.request(
          "api/jobs/\(id.number)/output/stream",
          query: [
            "host": id.host, "output_type": source, "chunk_size": "8192",
            "max_initial_bytes": String(OutputBuffer.limit),
          ])
        request.timeoutInterval = 3600
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        let (bytes, response) = try await api.session.bytes(for: request)
        try api.validate(response)
        var parser = SSEParser()
        var firstChunk = true
        var truncated = false
        connected = true
        loading = false
        error = nil
        for try await line in bytes.lines {
          try Task.checkCancellation()
          guard let event = parser.consume(line), let data = event.data(using: .utf8),
            let json = try? JSONDecoder().decode(JSONValue.self, from: data)
          else { continue }
          let fields = json.object
          switch fields.text("type") {
          case "chunk":
            guard !fields.flag("compressed") else {
              throw APIError(
                status: 0,
                message:
                  "This server uses a legacy compressed stream. Loading an output snapshot instead."
              )
            }
            let chunk = fields.text("data")
            if firstChunk {
              buffer.replace(chunk, truncated: truncated)
              firstChunk = false
            } else {
              buffer.append(chunk)
            }
            updatedAt = .now
            revision += 1
            if Date.now.timeIntervalSince(lastSaved) > 5 { saveSnapshot() }
          case "truncation_notice": truncated = true
          case "complete":
            complete = true
            connected = false
            return
          case "error":
            throw APIError(
              status: 0,
              message: fields.text(
                "message", fallback: fields.text("error", fallback: "Output is unavailable.")))
          default: break
          }
        }
        connected = false
        if Task.isCancelled { return }
        error = "Stream disconnected. Reconnecting…"
      } catch {
        if Task.isCancelled { return }
        self.error = error.localizedDescription
        connected = false
        loading = false
        do {
          let snapshot = try await api.output(id, source: source)
          buffer.replace(
            (source == "stdout" ? snapshot.stdout : snapshot.stderr) ?? "",
            truncated: snapshot.content_truncated == true)
          updatedAt = .now
          revision += 1
        } catch { self.error = error.localizedDescription }
      }
      do { try await Task.sleep(for: .seconds(5)) } catch { return }
    }
  }
}

struct OutputView: View {
  var id: JobID
  @Environment(AppStore.self) private var store
  @Environment(\.scenePhase) private var phase
  @State private var model = OutputModel()
  @State private var source = "stdout"
  @State private var query = ""
  @State private var follow = true
  @State private var wrap = true
  @State private var matchIndex = 0
  @State private var showBookmarks = false
  @State private var bookmarks: [OutputBookmark] = []
  @State private var exportURL: URL?
  @State private var exporting = false
  @State private var exportError: String?
  var bookmarkKey: String { "bookmarks.\(store.connection?.id.uuidString ?? "").\(id.id)" }
  var matches: [Int] { model.buffer.matchingLines(query) }
  var body: some View {
    VStack(spacing: 0) {
      VStack(alignment: .leading, spacing: 12) {
        HStack {
          Text(store.job(id)?.name ?? "#\(id.number)").font(.headline).lineLimit(1)
          Spacer()
          Circle().fill(model.connected ? Theme.green : Theme.secondary).frame(width: 6, height: 6)
          Text(model.complete ? "Finished" : model.connected ? "Streaming" : "Snapshot").font(
            .caption
          ).foregroundStyle(Theme.secondary)
        }
        HStack {
          Text("\(id.host) / #\(id.number)").font(.system(.caption, design: .monospaced))
          Spacer()
          Text(Format.age(model.updatedAt)).font(.caption)
        }.foregroundStyle(Theme.secondary)
        Picker("Output source", selection: $source) {
          Text("stdout").tag("stdout")
          Text("stderr").tag("stderr")
        }.pickerStyle(.segmented)
      }.padding(16).background(Theme.canvas)
      ScrollViewReader { proxy in
        VStack(spacing: 0) {
          if let error = model.error {
            HStack {
              Image(systemName: "wifi.exclamationmark")
              Text(error).lineLimit(2)
            }.font(.caption).foregroundStyle(Theme.amber).padding(10).frame(
              maxWidth: .infinity, alignment: .leading
            ).background(Theme.canvas)
          }
          if model.buffer.trimmed {
            Text(
              "Showing a bounded window. Search covers loaded text only; download for the complete file."
            )
            .font(.caption2).foregroundStyle(Theme.secondary).padding(10).frame(
              maxWidth: .infinity, alignment: .leading
            ).background(Theme.canvas)
          }
          HStack {
            Image(systemName: "magnifyingglass").foregroundStyle(Theme.secondary)
            TextField("Find in loaded output", text: $query).textInputAutocapitalization(.never)
              .autocorrectionDisabled()
              .accessibilityIdentifier("outputSearch")
            if !query.isEmpty {
              Text("\(matches.isEmpty ? 0 : min(matchIndex + 1, matches.count))/\(matches.count)")
                .font(.caption.monospacedDigit())
              Button("Previous match", systemImage: "chevron.up") { jump(-1, proxy: proxy) }
                .disabled(matches.isEmpty)
              Button("Next match", systemImage: "chevron.down") { jump(1, proxy: proxy) }.disabled(
                matches.isEmpty)
              Button("Clear", systemImage: "xmark.circle.fill") { query = "" }
            }
          }.font(.subheadline).padding(12).background(Theme.surface)
          ScrollView(wrap ? .vertical : [.vertical, .horizontal]) {
            LazyVStack(alignment: .leading, spacing: 0) {
              ForEach(Array(model.lines.enumerated()), id: \.offset) { index, line in
                HStack(alignment: .top, spacing: 12) {
                  Text("\(index + 1)").foregroundStyle(Color.white.opacity(0.3)).frame(
                    width: 38, alignment: .trailing
                  ).accessibilityHidden(true)
                  Text(line.isEmpty ? " " : line)
                    .foregroundStyle(
                      line.localizedCaseInsensitiveContains("error")
                        ? Color(red: 1, green: 0.60, blue: 0.55)
                        : Color(red: 0.80, green: 0.86, blue: 0.95)
                    )
                    .fixedSize(horizontal: !wrap, vertical: true).frame(
                      maxWidth: .infinity, alignment: .leading
                    )
                    .textSelection(.enabled)
                }.font(.system(size: 12, design: .monospaced)).padding(.vertical, 4).padding(
                  .trailing, 12
                )
                .background(
                  !query.isEmpty && line.localizedCaseInsensitiveContains(query)
                    ? Color.yellow.opacity(0.17) : Color.clear
                )
                .id(index).contextMenu {
                  Button("Bookmark line", systemImage: "bookmark") { addBookmark(line) }
                  Button("Copy line", systemImage: "doc.on.doc") {
                    UIPasteboard.general.string = line
                  }
                }
              }
              Color.clear.frame(height: 1).id("tail")
            }.padding(.vertical, 12)
          }.background(Color("CodeCanvas")).scrollDismissesKeyboard(.interactively)
            .onScrollPhaseChange { _, new in if new == .interacting { follow = false } }
            .onChange(of: model.revision) { _, _ in
              if follow { proxy.scrollTo("tail", anchor: .bottom) }
            }
            .overlay {
              if model.loading {
                ProgressView("Opening output…").padding().background(
                  Theme.surface, in: RoundedRectangle(cornerRadius: 12))
              }
            }
          HStack(spacing: 20) {
            Button {
              follow.toggle()
              if follow { proxy.scrollTo("tail", anchor: .bottom) }
            } label: {
              Label(
                follow ? "Following" : "Jump to latest",
                systemImage: follow ? "arrow.down.to.line.compact" : "arrow.down")
            }.font(.subheadline.weight(.semibold))
              .accessibilityIdentifier("outputFollow")
            Spacer(minLength: 0)
            Button("Bookmarks", systemImage: "bookmark") { showBookmarks = true }
            Menu {
              Toggle("Wrap lines", isOn: $wrap)
              Button("Add local marker", systemImage: "flag") {
                addBookmark(
                  "Marker at \(Date.now.formatted(date: .omitted, time: .standard)): \(model.lines.last ?? "")"
                )
              }
              Button("Download full \(source)", systemImage: "square.and.arrow.up") { export() }
                .disabled(exporting)
            } label: {
              Image(systemName: "ellipsis.circle")
            }.accessibilityLabel("Output options")
          }.padding(17).background(Theme.surface)
        }.onChange(of: query) { _, _ in
          matchIndex = 0
          follow = false
          if let first = matches.first { proxy.scrollTo(first, anchor: .center) }
        }
      }
    }.background(Theme.canvas).navigationTitle("Output").navigationBarTitleDisplayMode(.inline)
      .task(id: "\(source)-\(phase == .active)") {
        guard phase == .active else { return }
        let file = store.connection.map {
          store.storage.outputURL(connectionID: $0.id, job: id, source: source)
        }
        await model.watch(
          api: store.client, id: id, source: source, demo: store.demo, snapshotURL: file)
      }
      .onAppear {
        if let data = UserDefaults.standard.data(forKey: bookmarkKey),
          let saved = try? JSONDecoder().decode([OutputBookmark].self, from: data)
        {
          bookmarks = saved
        }
      }
      .onChange(of: source) { _, _ in
        follow = true
        query = ""
      }
      .sheet(isPresented: $showBookmarks) {
        NavigationStack {
          List {
            if bookmarks.isEmpty {
              Text("Long-press a line to bookmark it, or add a local marker from Output options.")
                .foregroundStyle(.secondary)
            }
            ForEach(bookmarks) { bookmark in
              Button {
                source = bookmark.source
                query = String(bookmark.excerpt.prefix(80))
                showBookmarks = false
              } label: {
                VStack(alignment: .leading, spacing: 7) {
                  Text(bookmark.excerpt).font(.system(.caption, design: .monospaced)).lineLimit(4)
                  Text("\(bookmark.source) · \(bookmark.createdAt.formatted())").font(.caption2)
                    .foregroundStyle(.secondary)
                }
              }
            }.onDelete {
              bookmarks.remove(atOffsets: $0)
              saveBookmarks()
            }
          }.navigationTitle("Local bookmarks").toolbar { Button("Done") { showBookmarks = false } }
        }
      }
      .sheet(isPresented: Binding(get: { exportURL != nil }, set: { if !$0 { exportURL = nil } })) {
        if let exportURL { ShareSheet(url: exportURL) }
      }
      .alert(
        "Download failed",
        isPresented: Binding(get: { exportError != nil }, set: { if !$0 { exportError = nil } })
      ) {
        Button("OK") {}
      } message: {
        Text(exportError ?? "")
      }
  }
  private func jump(_ delta: Int, proxy: ScrollViewProxy) {
    guard !matches.isEmpty else { return }
    matchIndex = (matchIndex + delta + matches.count) % matches.count
    follow = false
    proxy.scrollTo(matches[matchIndex], anchor: .center)
  }
  private func addBookmark(_ text: String) {
    bookmarks.append(OutputBookmark(source: source, excerpt: String(text.prefix(1000))))
    saveBookmarks()
  }
  private func saveBookmarks() {
    if let data = try? JSONEncoder().encode(bookmarks) {
      UserDefaults.standard.set(data, forKey: bookmarkKey)
    }
  }
  private func export() {
    exporting = true
    Task {
      defer { exporting = false }
      do {
        if store.demo {
          let file = FileManager.default.temporaryDirectory.appending(
            path: "ssync-demo-\(source).txt")
          try DemoData.output(source).write(to: file, atomically: true, encoding: .utf8)
          exportURL = file
        } else {
          exportURL = try await store.client?.download(id, source: source)
        }
      } catch { exportError = error.localizedDescription }
    }
  }
}
struct ShareSheet: UIViewControllerRepresentable {
  var url: URL
  func makeUIViewController(context: Context) -> UIActivityViewController {
    UIActivityViewController(activityItems: [url], applicationActivities: nil)
  }
  func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}
