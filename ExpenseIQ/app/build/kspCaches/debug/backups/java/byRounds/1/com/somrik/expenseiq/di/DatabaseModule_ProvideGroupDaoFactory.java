package com.somrik.expenseiq.di;

import com.somrik.expenseiq.data.db.AppDatabase;
import com.somrik.expenseiq.data.db.dao.AccountGroupDao;
import dagger.internal.DaggerGenerated;
import dagger.internal.Factory;
import dagger.internal.Preconditions;
import dagger.internal.QualifierMetadata;
import dagger.internal.ScopeMetadata;
import javax.annotation.processing.Generated;
import javax.inject.Provider;

@ScopeMetadata
@QualifierMetadata
@DaggerGenerated
@Generated(
    value = "dagger.internal.codegen.ComponentProcessor",
    comments = "https://dagger.dev"
)
@SuppressWarnings({
    "unchecked",
    "rawtypes",
    "KotlinInternal",
    "KotlinInternalInJava",
    "cast"
})
public final class DatabaseModule_ProvideGroupDaoFactory implements Factory<AccountGroupDao> {
  private final Provider<AppDatabase> dbProvider;

  public DatabaseModule_ProvideGroupDaoFactory(Provider<AppDatabase> dbProvider) {
    this.dbProvider = dbProvider;
  }

  @Override
  public AccountGroupDao get() {
    return provideGroupDao(dbProvider.get());
  }

  public static DatabaseModule_ProvideGroupDaoFactory create(Provider<AppDatabase> dbProvider) {
    return new DatabaseModule_ProvideGroupDaoFactory(dbProvider);
  }

  public static AccountGroupDao provideGroupDao(AppDatabase db) {
    return Preconditions.checkNotNullFromProvides(DatabaseModule.INSTANCE.provideGroupDao(db));
  }
}
