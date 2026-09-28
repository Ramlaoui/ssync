import Observation
import SwiftUI

@MainActor @Observable final class OutputModel {
  var buffer = OutputBuffer() {
    didSet { lines = buffer.text.components(separatedBy: "\n") }
  }
  /// Split once per change rather than on every render.
  private(set) var lines: [String] = [""]
  var connected = false
  var loading = true
  var error: String?
  var revision = 0
  var updatedAt: Date?
  var complete = false

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
        var splitter = SSELineSplitter()
        var parser = SSEParser()
        var firstChunk = true
        var truncated = false
        connected = true
        loading = false
        error = nil
        for try await byte in bytes {
          guard let line = splitter.feed(byte) else { continue }
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
  @State private var searching = false
  @State private var query = ""
  @State private var matches: [Int] = []
  @State private var matchIndex = 0
  @State private var follow = true
  @State private var pausedAt = 0
  @State private var wrap = true
  @State private var showBookmarks = false
  @State private var bookmarks: [OutputBookmark] = []
  @State private var exportURL: URL?
  @State private var exporting = false
  @State private var exportError: String?
  @FocusState private var findFocused: Bool
  var bookmarkKey: String { "bookmarks.\(store.connection?.id.uuidString ?? "").\(id.id)" }
  var unseen: Int { max(0, model.lines.count - pausedAt) }
  var status: String {
    let live = model.complete ? "Finished" : model.connected ? "Live" : "Snapshot"
    return "\(source) · \(live) · \(Format.age(model.updatedAt).lowercased())"
  }

  var body: some View {
    ScrollViewReader { proxy in
      VStack(spacing: 0) {
        if let notice {
          Label(notice.text, systemImage: notice.symbol).font(.caption)
            .foregroundStyle(notice.warning ? Theme.amber : .secondary).lineLimit(2)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 16).padding(.vertical, 8).background(.bar)
        }
        if searching { findBar(proxy) }
        log
          .onScrollPhaseChange { _, new in
            if new == .interacting && follow {
              follow = false
              pausedAt = model.lines.count
            }
          }
          .onChange(of: model.revision) { _, _ in
            if follow { proxy.scrollTo("tail", anchor: .bottom) }
            if !query.isEmpty { matches = model.buffer.matchingLines(query) }
          }
          .onChange(of: query) { _, _ in
            matches = query.isEmpty ? [] : model.buffer.matchingLines(query)
            matchIndex = 0
            if let first = matches.first {
              follow = false
              pausedAt = model.lines.count
              proxy.scrollTo(first, anchor: .center)
            }
          }
      }
      .toolbar {
        ToolbarItem(placement: .bottomBar) {
          Picker("Output source", selection: $source) {
            Text("stdout").tag("stdout")
            Text("stderr").tag("stderr")
          }.pickerStyle(.segmented).fixedSize()
        }
        ToolbarSpacer(.flexible, placement: .bottomBar)
        ToolbarItem(placement: .bottomBar) {
          Button {
            follow.toggle()
            if follow {
              proxy.scrollTo("tail", anchor: .bottom)
            } else {
              pausedAt = model.lines.count
            }
          } label: {
            if follow {
              Label("Following", systemImage: "arrow.down.to.line")
            } else {
              Label(
                unseen > 0 ? "\(unseen) new lines" : "Jump to latest", systemImage: "arrow.down")
            }
          }
          .labelStyle(.titleAndIcon)
          .accessibilityIdentifier("outputFollow")
        }
      }
    }
    .toolbar(.hidden, for: .tabBar)
    .navigationTitle(store.job(id)?.name ?? "#\(id.number)")
    .navigationSubtitle(status)
    .navigationBarTitleDisplayMode(.inline)
    .toolbar {
      ToolbarItem(placement: .topBarTrailing) {
        Button("Find", systemImage: "magnifyingglass") {
          searching.toggle()
          findFocused = searching
          if !searching { query = "" }
        }.accessibilityIdentifier("outputFind")
      }
      ToolbarItem(placement: .topBarTrailing) { optionsMenu }
    }
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
    .sheet(isPresented: $showBookmarks) { bookmarkSheet }
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

  private var notice: (text: String, symbol: String, warning: Bool)? {
    if let error = model.error { return (error, "wifi.exclamationmark", true) }
    if model.buffer.trimmed {
      return (
        "Showing the latest part of the file. Download for the full output.", "scissors", false
      )
    }
    return nil
  }

  private var log: some View {
    ScrollView(wrap ? .vertical : [.vertical, .horizontal]) {
      LazyVStack(alignment: .leading, spacing: 0) {
        ForEach(model.lines.indices, id: \.self) { index in
          let line = model.lines[index]
          HStack(alignment: .top, spacing: 10) {
            Text("\(index + 1)").foregroundStyle(.tertiary)
              .frame(minWidth: 30, alignment: .trailing).accessibilityHidden(true)
            Text(line.isEmpty ? " " : line)
              .foregroundStyle(tone(line))
              .fixedSize(horizontal: !wrap, vertical: true)
              .frame(maxWidth: .infinity, alignment: .leading)
              .textSelection(.enabled)
          }
          .font(.system(size: 12, design: .monospaced)).padding(.vertical, 2).padding(.trailing, 12)
          .background(highlight(index))
          .id(index)
          .contextMenu {
            Button("Copy line", systemImage: "doc.on.doc") { UIPasteboard.general.string = line }
            Button("Bookmark line", systemImage: "bookmark") { addBookmark(line) }
          }
        }
        Color.clear.frame(height: 1).id("tail")
      }.padding(.vertical, 10)
    }
    .background(Theme.code)
    .scrollDismissesKeyboard(.interactively)
    .overlay {
      if model.loading { ProgressView() }
    }
  }
  private func tone(_ line: String) -> Color {
    let lower = line.lowercased()
    if lower.contains("error") || lower.contains("traceback") { return Theme.red }
    if lower.contains("warn") { return Theme.amber }
    return .primary
  }
  private func highlight(_ index: Int) -> Color {
    guard !matches.isEmpty else { return .clear }
    if matches.indices.contains(matchIndex), matches[matchIndex] == index {
      return Color.yellow.opacity(0.35)
    }
    return matches.contains(index) ? Color.yellow.opacity(0.14) : .clear
  }

  private func findBar(_ proxy: ScrollViewProxy) -> some View {
    HStack(spacing: 12) {
      Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
      TextField("Find in output", text: $query).textInputAutocapitalization(.never)
        .autocorrectionDisabled().focused($findFocused).submitLabel(.search)
        .onSubmit { jump(1, proxy: proxy) }
        .accessibilityIdentifier("outputSearch")
      if !query.isEmpty {
        Text("\(matches.isEmpty ? 0 : matchIndex + 1)/\(matches.count)")
          .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
        Button("Previous match", systemImage: "chevron.up") { jump(-1, proxy: proxy) }
          .disabled(matches.isEmpty)
        Button("Next match", systemImage: "chevron.down") { jump(1, proxy: proxy) }
          .disabled(matches.isEmpty)
      }
    }
    .labelStyle(.iconOnly).font(.subheadline)
    .padding(.horizontal, 16).padding(.vertical, 10).background(.bar)
  }

  private var optionsMenu: some View {
    Menu {
      Toggle("Wrap lines", systemImage: "text.alignleft", isOn: $wrap)
      Button("Bookmarks", systemImage: "bookmark") { showBookmarks = true }
      Button("Add marker at end", systemImage: "flag") {
        addBookmark(
          "Marker at \(Date.now.formatted(date: .omitted, time: .standard)): \(model.lines.last ?? "")"
        )
      }
      Divider()
      Button("Download full \(source)", systemImage: "square.and.arrow.down") { export() }
        .disabled(exporting)
    } label: {
      Label("Output options", systemImage: "ellipsis")
    }
  }

  private var bookmarkSheet: some View {
    NavigationStack {
      List {
        ForEach(bookmarks) { bookmark in
          Button {
            source = bookmark.source
            searching = true
            query = String(bookmark.excerpt.prefix(80))
            showBookmarks = false
          } label: {
            VStack(alignment: .leading, spacing: 6) {
              Text(bookmark.excerpt).font(.system(.caption, design: .monospaced)).lineLimit(4)
              Text("\(bookmark.source) · \(bookmark.createdAt.formatted())").font(.caption2)
                .foregroundStyle(.secondary)
            }
          }.tint(.primary)
        }.onDelete {
          bookmarks.remove(atOffsets: $0)
          saveBookmarks()
        }
      }
      .overlay {
        if bookmarks.isEmpty {
          ContentUnavailableView(
            "No bookmarks", systemImage: "bookmark",
            description: Text("Long-press a line to bookmark it."))
        }
      }
      .navigationTitle("Bookmarks").navigationBarTitleDisplayMode(.inline)
      .toolbar { Button("Done") { showBookmarks = false } }
    }.presentationDetents([.medium, .large])
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
