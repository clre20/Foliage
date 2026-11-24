pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenLocal()
        maven("https://repo.papermc.io/repository/maven-public/")
    }
}

plugins {
    id("org.gradle.toolchains.foojay-resolver-convention") version "1.0.0"
}

rootProject.name = "foliage"

include("foliage-api")
include("foliage-server")
include("foliage-checkstyle")

gradle.lifecycle.beforeProject {
    val mcVersion = providers.gradleProperty("mcVersion").get().trim()
    val channel = providers.gradleProperty("channel").get().trim()
    val buildNumber = providers.environmentVariable("BUILD_NUMBER").orNull?.trim()?.takeIf { it.isNotEmpty() }
    // Same format as Paper: plugins (e.g. Essentials) parse Bukkit#getBukkitVersion with it.
    // The release jar is renamed to Foliage-<mc>-<build>.jar by the GitHub workflow.
    // Local builds use build 0 with the "local" channel instead of Paper's "<mc>.local-SNAPSHOT": some plugins
    // (e.g. AuraSkills) only understand the ".build." form.
    version = "$mcVersion.build.${buildNumber ?: "0"}-${if (buildNumber == null) "local" else channel.lowercase()}"
}
