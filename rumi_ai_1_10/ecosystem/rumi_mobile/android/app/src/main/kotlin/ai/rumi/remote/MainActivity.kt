package ai.rumi.remote

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.nio.ByteBuffer
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class MainActivity : FlutterActivity() {
    private var pendingNotificationPermissionResult: ((Boolean) -> Unit)? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        registerSecureStorageChannel(flutterEngine)
        registerPreferencesChannel(flutterEngine)
        registerUrlLauncherChannel(flutterEngine)
        registerNotificationsChannel(flutterEngine)
    }

    private fun registerSecureStorageChannel(flutterEngine: FlutterEngine) {
        val storage = RumiSecureStorage(this)
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "ai.rumi.remote/secure_storage",
        ).setMethodCallHandler { call, result ->
            val args = call.arguments as? Map<*, *>
            val key = args?.get("key") as? String
            if (key.isNullOrBlank()) {
                result.error("invalid_args", "Missing key", null)
                return@setMethodCallHandler
            }

            try {
                when (call.method) {
                    "read" -> result.success(storage.read(key))
                    "write" -> {
                        val value = args["value"] as? String
                        if (value == null) {
                            result.error("invalid_args", "Missing value", null)
                        } else {
                            storage.write(key, value)
                            result.success(null)
                        }
                    }
                    "delete" -> {
                        storage.delete(key)
                        result.success(null)
                    }
                    else -> result.notImplemented()
                }
            } catch (e: Exception) {
                result.error("secure_storage_failed", e.message, null)
            }
        }
    }

    private fun registerPreferencesChannel(flutterEngine: FlutterEngine) {
        val prefs = getSharedPreferences("rumi_preferences", Context.MODE_PRIVATE)
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "ai.rumi.remote/preferences",
        ).setMethodCallHandler { call, result ->
            val args = call.arguments as? Map<*, *>
            val key = args?.get("key") as? String
            if (key.isNullOrBlank()) {
                result.error("invalid_args", "Missing key", null)
                return@setMethodCallHandler
            }

            when (call.method) {
                "read" -> result.success(prefs.getString(key, null))
                "write" -> {
                    val value = args["value"] as? String
                    if (value == null) {
                        result.error("invalid_args", "Missing value", null)
                    } else {
                        prefs.edit().putString(key, value).apply()
                        result.success(null)
                    }
                }
                "delete" -> {
                    prefs.edit().remove(key).apply()
                    result.success(null)
                }
                else -> result.notImplemented()
            }
        }
    }

    private fun registerUrlLauncherChannel(flutterEngine: FlutterEngine) {
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "ai.rumi.remote/url_launcher",
        ).setMethodCallHandler { call, result ->
            if (call.method != "open") {
                result.notImplemented()
                return@setMethodCallHandler
            }
            val args = call.arguments as? Map<*, *>
            val raw = args?.get("url") as? String
            if (raw.isNullOrBlank()) {
                result.success(false)
                return@setMethodCallHandler
            }
            try {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(raw)))
                result.success(true)
            } catch (e: Exception) {
                result.success(false)
            }
        }
    }

    private fun registerNotificationsChannel(flutterEngine: FlutterEngine) {
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "ai.rumi.remote/notifications",
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                "requestAuthorization" -> {
                    requestNotificationAuthorization { granted ->
                        result.success(granted)
                    }
                }
                "showPcTaskFinished" -> {
                    val args = call.arguments as? Map<*, *>
                    val title = (args?.get("title") as? String)
                        ?.trim()
                        ?.takeIf { it.isNotEmpty() }
                        ?: "PCタスクが完了しました"
                    val body = (args?.get("body") as? String)
                        ?.trim()
                        ?.takeIf { it.isNotEmpty() }
                        ?: "PCのタスクが完了しました"
                    requestNotificationAuthorization { granted ->
                        if (!granted) {
                            result.success(false)
                        } else {
                            showPcTaskFinishedNotification(title, body)
                            result.success(true)
                        }
                    }
                }
                else -> result.notImplemented()
            }
        }
    }

    private fun requestNotificationAuthorization(callback: (Boolean) -> Unit) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            callback(true)
            return
        }
        if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) {
            callback(true)
            return
        }
        if (pendingNotificationPermissionResult != null) {
            callback(false)
            return
        }
        pendingNotificationPermissionResult = callback
        requestPermissions(
            arrayOf(Manifest.permission.POST_NOTIFICATIONS),
            REQUEST_POST_NOTIFICATIONS,
        )
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQUEST_POST_NOTIFICATIONS) return
        val granted = grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED
        val callback = pendingNotificationPermissionResult
        pendingNotificationPermissionResult = null
        callback?.invoke(granted)
    }

    private fun showPcTaskFinishedNotification(title: String, body: String) {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                NOTIFICATION_CHANNEL_ID,
                "Rumi PC Tasks",
                NotificationManager.IMPORTANCE_DEFAULT,
            )
            manager.createNotificationChannel(channel)
        }

        val intent = packageManager.getLaunchIntentForPackage(packageName)
            ?: Intent(this, MainActivity::class.java)
        intent.flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or immutablePendingIntentFlag(),
        )
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, NOTIFICATION_CHANNEL_ID)
        } else {
            Notification.Builder(this)
        }
        val notification = builder
            .setSmallIcon(android.R.drawable.stat_sys_download_done)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(Notification.BigTextStyle().bigText(body))
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .build()
        manager.notify((System.currentTimeMillis() % Int.MAX_VALUE).toInt(), notification)
    }

    private fun immutablePendingIntentFlag(): Int {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            PendingIntent.FLAG_IMMUTABLE
        } else {
            0
        }
    }

    private companion object {
        const val REQUEST_POST_NOTIFICATIONS = 7401
        const val NOTIFICATION_CHANNEL_ID = "rumi_pc_tasks"
    }
}

private class RumiSecureStorage(context: Context) {
    private val prefs = context.getSharedPreferences("rumi_secure_storage", Context.MODE_PRIVATE)

    fun read(key: String): String? {
        val encoded = prefs.getString(key, null) ?: return null
        val payload = Base64.decode(encoded, Base64.NO_WRAP)
        if (payload.size < IV_SIZE + 1) return null
        val iv = payload.copyOfRange(0, IV_SIZE)
        val ciphertext = payload.copyOfRange(IV_SIZE, payload.size)
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(TAG_SIZE_BITS, iv))
        return String(cipher.doFinal(ciphertext), Charsets.UTF_8)
    }

    fun write(key: String, value: String) {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
        val ciphertext = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        val payload = ByteBuffer.allocate(cipher.iv.size + ciphertext.size)
            .put(cipher.iv)
            .put(ciphertext)
            .array()
        prefs.edit().putString(key, Base64.encodeToString(payload, Base64.NO_WRAP)).apply()
    }

    fun delete(key: String) {
        prefs.edit().remove(key).apply()
    }

    private fun secretKey(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val existing = keyStore.getEntry(KEY_ALIAS, null) as? KeyStore.SecretKeyEntry
        if (existing != null) return existing.secretKey

        val keyGenerator = KeyGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_AES,
            "AndroidKeyStore",
        )
        keyGenerator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build(),
        )
        return keyGenerator.generateKey()
    }

    private companion object {
        const val KEY_ALIAS = "rumi_remote_secure_storage"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val IV_SIZE = 12
        const val TAG_SIZE_BITS = 128
    }
}
