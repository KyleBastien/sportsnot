#!/usr/bin/env ruby
# frozen_string_literal: true

# Sets up the SportsNotWidget Widget Extension target in ios/App/App.xcodeproj
# and wires in all native Swift sources living under ios/ (outside of the
# Capacitor-generated ios/App folder).
#
# Idempotent: re-running won't duplicate target/file references.
#
# Requirements: gem install xcodeproj

require "xcodeproj"
require "pathname"

REPO         = Pathname.new(File.expand_path("../..", __dir__))
PROJECT_PATH = REPO.join("ios/App/App.xcodeproj")
PROJECT      = Xcodeproj::Project.open(PROJECT_PATH.to_s)

APP_TARGET_NAME    = "App"
WIDGET_TARGET_NAME = "SportsNotWidget"
APP_BUNDLE_ID      = "com.sportsnot.app"
WIDGET_BUNDLE_ID   = "#{APP_BUNDLE_ID}.SportsNotWidget"
APP_GROUP          = "group.com.sportsnot.widget"
DEPLOYMENT_TARGET  = "17.0"

app_target = PROJECT.targets.find { |t| t.name == APP_TARGET_NAME } or
  abort("Could not find App target")

# --- Ensure or create the Widget Extension target ---------------------------
widget_target = PROJECT.targets.find { |t| t.name == WIDGET_TARGET_NAME }

if widget_target.nil?
  puts "Creating Widget Extension target: #{WIDGET_TARGET_NAME}"
  widget_target = PROJECT.new_target(
    :app_extension,
    WIDGET_TARGET_NAME,
    :ios,
    DEPLOYMENT_TARGET,
  )
else
  puts "Widget target already exists; updating settings"
end

# --- Helpers ----------------------------------------------------------------
def add_group(parent_group, name, real_path)
  existing = parent_group.groups.find { |g| g.name == name || g.path == name }
  return existing if existing

  parent_group.new_group(name, real_path.to_s)
end

def add_file_to_target(project, group, file_path, targets)
  relative = file_path.relative_path_from(Pathname.new(group.real_path))
  ref = group.files.find { |f| f.real_path == file_path }
  ref ||= group.new_file(relative.to_s)
  Array(targets).each do |t|
    already = t.source_build_phase.files_references.include?(ref)
    t.add_file_references([ref]) unless already
  end
  ref
end

# --- Group layout under the project main group -----------------------------
main_group = PROJECT.main_group
widget_ext_group = add_group(
  main_group,
  "WidgetExtension",
  REPO.join("ios/WidgetExtension"),
)
widget_views_group = add_group(
  widget_ext_group,
  "Views",
  REPO.join("ios/WidgetExtension/Views"),
)
shared_group = add_group(
  main_group,
  "SportsNotWidgetShared",
  REPO.join("ios/SportsNotWidgetShared"),
)
plugin_group = add_group(
  main_group,
  "WidgetBridgePlugin",
  REPO.join("ios/CapacitorPlugins/WidgetBridge"),
)
widget_resources_group = add_group(
  main_group,
  "SportsNotWidget",
  REPO.join("ios/App/SportsNotWidget"),
)

# --- Add source files -------------------------------------------------------
Dir[REPO.join("ios/WidgetExtension/*.swift").to_s].sort.each do |path|
  add_file_to_target(PROJECT, widget_ext_group, Pathname.new(path), widget_target)
end
Dir[REPO.join("ios/WidgetExtension/Views/*.swift").to_s].sort.each do |path|
  add_file_to_target(PROJECT, widget_views_group, Pathname.new(path), widget_target)
end
# Shared -> BOTH targets
Dir[REPO.join("ios/SportsNotWidgetShared/*.swift").to_s].sort.each do |path|
  add_file_to_target(PROJECT, shared_group, Pathname.new(path), [app_target, widget_target])
end
# Plugin -> App target only
Dir[REPO.join("ios/CapacitorPlugins/WidgetBridge/*.swift").to_s].sort.each do |path|
  add_file_to_target(PROJECT, plugin_group, Pathname.new(path), app_target)
end

# MainViewController.swift (App target only) - subclass of CAPBridgeViewController
# that registers plugins compiled directly into the app (Capacitor v6 only
# auto-discovers plugins from installed pods).
app_group_for_mvc = main_group.children.find { |g| g.respond_to?(:name) && g.name == "App" } || main_group["App"]
if app_group_for_mvc
  mvc_path = REPO.join("ios/App/App/MainViewController.swift")
  unless app_group_for_mvc.files.any? { |f| f.real_path == mvc_path }
    file_ref = app_group_for_mvc.new_file("MainViewController.swift")
    app_target.source_build_phase.add_file_reference(file_ref) unless app_target.source_build_phase.files_references.include?(file_ref)
  end
end

# --- Widget Info.plist + entitlements file references (not in sources) -----
widget_info_plist = REPO.join("ios/App/SportsNotWidget/Info.plist")
widget_entitlements = REPO.join("ios/App/SportsNotWidget/SportsNotWidget.entitlements")
app_entitlements = REPO.join("ios/App/App/App.entitlements")

[widget_info_plist, widget_entitlements].each do |path|
  rel = path.relative_path_from(Pathname.new(widget_resources_group.real_path))
  next if widget_resources_group.files.any? { |f| f.real_path == path }

  widget_resources_group.new_file(rel.to_s)
end

app_group_grp = main_group.children.find { |g| g.respond_to?(:name) && g.name == "App" } || main_group["App"]
if app_group_grp && !app_group_grp.files.any? { |f| f.real_path == app_entitlements }
  rel = app_entitlements.relative_path_from(Pathname.new(app_group_grp.real_path))
  app_group_grp.new_file(rel.to_s)
end

# --- Build settings --------------------------------------------------------
widget_info_plist_rel = "SportsNotWidget/Info.plist"
widget_entitlements_rel = "SportsNotWidget/SportsNotWidget.entitlements"
app_entitlements_rel = "App/App.entitlements"

widget_target.build_configurations.each do |config|
  s = config.build_settings
  s["PRODUCT_BUNDLE_IDENTIFIER"] = WIDGET_BUNDLE_ID
  s["PRODUCT_NAME"]              = WIDGET_TARGET_NAME
  s["IPHONEOS_DEPLOYMENT_TARGET"] = DEPLOYMENT_TARGET
  s["INFOPLIST_FILE"]            = widget_info_plist_rel
  s["CODE_SIGN_ENTITLEMENTS"]    = widget_entitlements_rel
  s["SKIP_INSTALL"]              = "YES"
  s["SWIFT_VERSION"]             = "5.0"
  s["TARGETED_DEVICE_FAMILY"]    = "1,2"
  s["LD_RUNPATH_SEARCH_PATHS"]   = "$(inherited) @executable_path/Frameworks @executable_path/../../Frameworks"
  s["GENERATE_INFOPLIST_FILE"]   = "NO"
  s["CURRENT_PROJECT_VERSION"]   = "1"
  s["MARKETING_VERSION"]         = "1.0"
  s["SUPABASE_URL"]              ||= "$(SUPABASE_URL)"
  s["SUPABASE_ANON_KEY"]         ||= "$(SUPABASE_ANON_KEY)"
end

app_target.build_configurations.each do |config|
  s = config.build_settings
  s["CODE_SIGN_ENTITLEMENTS"]     = app_entitlements_rel
  s["IPHONEOS_DEPLOYMENT_TARGET"] = DEPLOYMENT_TARGET
  s["SUPABASE_URL"]              ||= "$(SUPABASE_URL)"
  s["SUPABASE_ANON_KEY"]         ||= "$(SUPABASE_ANON_KEY)"
end

# --- Link required frameworks to widget target -----------------------------
required_frameworks = %w[SwiftUI.framework WidgetKit.framework ActivityKit.framework AppIntents.framework]
frameworks_group = PROJECT.frameworks_group || main_group.new_group("Frameworks")
required_frameworks.each do |fw|
  ref = frameworks_group.files.find { |f| f.name == fw || f.path&.end_with?(fw) }
  if ref.nil?
    ref = frameworks_group.new_reference("System/Library/Frameworks/#{fw}")
    ref.source_tree = "SDKROOT"
    ref.name = fw
  end
  unless widget_target.frameworks_build_phase.files_references.include?(ref)
    widget_target.frameworks_build_phase.add_file_reference(ref)
  end
end

# --- Embed widget extension in App target ----------------------------------
embed_phase = app_target.copy_files_build_phases.find { |p| p.name == "Embed App Extensions" }
if embed_phase.nil?
  embed_phase = app_target.new_copy_files_build_phase("Embed App Extensions")
  embed_phase.symbol_dst_subfolder_spec = :plug_ins
end
widget_product = widget_target.product_reference
unless embed_phase.files_references.include?(widget_product)
  build_file = embed_phase.add_file_reference(widget_product)
  build_file.settings = { "ATTRIBUTES" => ["RemoveHeadersOnCopy"] }
end

# --- App target depends on widget target -----------------------------------
unless app_target.dependencies.map(&:target).include?(widget_target)
  app_target.add_dependency(widget_target)
end

# --- Ensure shared scheme for widget ---------------------------------------
schemes_dir = File.join(PROJECT_PATH.to_s, "xcshareddata", "xcschemes")
scheme_path = File.join(schemes_dir, "#{WIDGET_TARGET_NAME}.xcscheme")
unless File.exist?(scheme_path)
  scheme = Xcodeproj::XCScheme.new
  scheme.add_build_target(widget_target)
  scheme.set_launch_target(widget_target)
  scheme.save_as(PROJECT_PATH.to_s, WIDGET_TARGET_NAME, true)
end

PROJECT.save
puts "Saved #{PROJECT_PATH}"
