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
    val buildNumber = providers.environmentVariable("BUILD_NUMBER").orNull?.trim()?.takeIf { it.isNotEmpty() }
    version = "$mcVersion-${buildNumber ?: "DEV"}"
}
